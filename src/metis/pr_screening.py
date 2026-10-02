"""External PR screening: gather evidence, judge criteria, apply a bounded action."""

import base64
import hashlib
import json
from urllib.parse import quote

from ._http import APIError, probability

from .engine import Step, Workflow
from .github import GitHub
from .jev import Jev


def validate_config(config):
    for key in ("minimum_pass_probability", "maximum_fail_probability"):
        probability(config[key], key)
    if not config["maximum_fail_probability"] < config["minimum_pass_probability"]:
        raise ValueError("Failure threshold must be lower than the pass threshold.")
    for key, ceiling in (("max_changed_files", 3000), ("max_input_characters", 100000)):
        if type(config[key]) is not int or not 0 < config[key] <= ceiling:
            raise ValueError("Invalid PR input budget.")
    criteria = config["criteria"]
    if not isinstance(criteria, dict) or not 1 <= len(criteria) <= 32:
        raise ValueError("Configure between 1 and 32 PR criteria.")
    if any(not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
           for k, v in criteria.items()):
        raise ValueError("Each criterion needs a name and a yes/no question.")
    if not isinstance(config["allow_authors"], list) or any(
        not isinstance(author, str) or not author.strip() for author in config["allow_authors"]
    ):
        raise ValueError("allow_authors must be a list of usernames.")
    for key in ("repository_context", "close_comment"):
        if not isinstance(config[key], str):
            raise ValueError("Repository context and close comment must be strings.")
    if len(config["close_comment"]) > 10000:
        raise ValueError("Close comment is too long.")
    return config


def snapshot(pr):
    return {
        "state": pr["state"], "title": pr["title"], "body": pr.get("body"),
        "head": pr["head"]["sha"], "base": pr["base"]["sha"],
        "base_ref": pr["base"]["ref"], "draft": pr["draft"],
        "association": pr.get("author_association"), "author": pr["user"]["login"],
        "labels": sorted(label["name"] for label in pr["labels"]),
    }


def load_pull_request(ctx):
    event = ctx.event
    if event.get("action") not in {"opened", "reopened", "synchronize", "edited", "ready_for_review"}:
        ctx.skip("Unsupported PR event.")
    if "pull_request" not in event:
        ctx.skip("Not a pull request event.")
    validate_config(ctx.config)
    repository = event["repository"]["full_name"]
    number = event["pull_request"]["number"]
    if type(number) is not int or number <= 0:
        raise ValueError("Invalid PR number.")
    gh = ctx.services.setdefault("github", GitHub(repository, dry_run=ctx.dry_run))
    pr = gh.request(f"/pulls/{number}")
    if pr["base"]["repo"]["full_name"] != repository:
        raise ValueError("PR base repository does not match event repository.")
    if pr["state"] != "open" or pr["draft"]:
        ctx.skip("PR is closed or a draft.")
    association = pr.get("author_association")
    if association not in {"OWNER", "MEMBER", "COLLABORATOR", "CONTRIBUTOR", "FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR", "NONE"}:
        ctx.skip("Author association is unknown; manual review is needed.")
    if association in {"OWNER", "MEMBER"}:
        ctx.skip("PR author belongs to the repository owner or organization.")
    if pr["user"]["type"] == "Bot" or pr["user"]["login"].casefold() in {
        author.casefold() for author in ctx.config["allow_authors"]
    }:
        ctx.skip("PR author is exempt from screening.")
    if pr["changed_files"] > ctx.config["max_changed_files"]:
        ctx.skip("PR exceeds the file budget; manual review is needed.")
    # Keep full PR data out of the public run report.
    ctx.services["pull_request"] = pr
    return {"number": number, "head_sha": pr["head"]["sha"]}


def gather_evidence(ctx):
    gh = ctx.services["github"]
    pr = ctx.services["pull_request"]
    repo = gh.request()
    readme = ""
    try:
        content = gh.request("/readme?ref=" + quote(pr["base"]["sha"], safe=""))
        if content.get("encoding") == "base64" and content["size"] <= 20000:
            readme = base64.b64decode(content["content"]).decode("utf-8")
    except APIError as error:
        if error.status != 404:
            raise
    files = gh.pages(f"/pulls/{pr['number']}/files", max_items=ctx.config["max_changed_files"])
    if len(files) != pr["changed_files"]:
        ctx.skip("Changed-file evidence is incomplete; manual review is needed.")
    evidence = []
    for file in files:
        patch = file.get("patch")
        if patch is None:
            if file["status"] == "renamed" and file["changes"] == 0:
                patch = ""
            else:
                ctx.skip("A file has no readable patch; manual review is needed.")
        # GitHub may truncate large patches. Do not close on a partial diff.
        added = sum(line.startswith("+") for line in patch.splitlines())
        removed = sum(line.startswith("-") for line in patch.splitlines())
        if added != file["additions"] or removed != file["deletions"]:
            ctx.skip("A patch is incomplete; manual review is needed.")
        evidence.append({key: file.get(key) for key in (
            "filename", "previous_filename", "status", "additions", "deletions"
        )} | {"patch": patch})
    state = {
        "repository": {"name": repo["full_name"], "description": repo.get("description"),
                       "readme": readme, "contribution_context": ctx.config["repository_context"]},
        "pull_request": {"title": pr["title"], "body": pr.get("body") or ""},
        "files": evidence,
    }
    if len(json.dumps(state, ensure_ascii=False)) > ctx.config["max_input_characters"]:
        ctx.skip("PR exceeds the input budget; manual review is needed.")
    ctx.services["evidence"] = state
    return {"files_reviewed": len(files)}


def judge(ctx):
    jev = ctx.services.setdefault("jev", Jev())
    criteria = {name: text + " If the evidence does not establish a yes or a no, "
                "use an uncertain probability rather than assuming a violation."
                for name, text in ctx.config["criteria"].items()}
    answers = jev.check(ctx.services["evidence"], criteria)
    # Validate even injected service responses before allowing a close.
    probabilities = {name: probability(answers[name], name) for name in criteria}
    failed = [name for name, value in probabilities.items()
              if value <= ctx.config["maximum_fail_probability"]]
    decision = "close" if failed else (
        "keep_open" if all(value >= ctx.config["minimum_pass_probability"]
                           for value in probabilities.values()) else "needs_review"
    )
    return {"decision": decision, "probabilities": probabilities, "failed_criteria": failed}


def apply_decision(ctx):
    decision = ctx.outputs["judge"]
    if decision["decision"] != "close":
        return {"action": "left_open", "reason": decision["decision"]}
    gh = ctx.services["github"]
    pr = ctx.services["pull_request"]
    path = f"/pulls/{pr['number']}"
    current = gh.request(path)
    if snapshot(current) != snapshot(pr) or current["updated_at"] != pr["updated_at"]:
        ctx.skip("PR changed during screening; no close was applied.")
    if ctx.dry_run:
        return {"action": "would_close", "failed_criteria": decision["failed_criteria"]}
    policy_hash = hashlib.sha256(json.dumps(ctx.config, sort_keys=True).encode()).hexdigest()[:16]
    marker = f"<!-- metis-pr-screening:{pr['head']['sha']}:{policy_hash} -->"
    comment = ctx.config["close_comment"].strip()
    if comment:
        comments = gh.pages(f"/issues/{pr['number']}/comments")
        if not any(item.get("user", {}).get("type") == "Bot" and marker in (item.get("body") or "")
                   for item in comments):
            gh.request(f"/issues/{pr['number']}/comments", method="POST", payload={
                "body": marker + "\n" + comment + "\n\nFailed criteria:\n" + "\n".join(
                    "- " + ctx.config["criteria"][name] for name in decision["failed_criteria"]
                ),
            })
    # Posting a comment may update updated_at. Recheck content and commits again.
    if snapshot(gh.request(path)) != snapshot(pr):
        ctx.skip("PR changed before closure; no close was applied.")
    gh.request(path, method="PATCH", payload={"state": "closed"})
    return {"action": "closed", "failed_criteria": decision["failed_criteria"]}


def workflow(name="pr-screening"):
    return Workflow(name, (
        Step("load", load_pull_request), Step("evidence", gather_evidence),
        Step("judge", judge), Step("apply", apply_decision),
    ))
