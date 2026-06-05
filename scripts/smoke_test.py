#!/usr/bin/env python
"""Live end-to-end smoke test for linear-python-client.

Exercises every public :class:`LinearClient` method against the real Linear API.
For every mutation it re-pulls the affected issue (or its comments) and asserts the
change actually landed. A clearly-labelled test issue is created and archived at the
end, so the script is self-cleaning.

This talks to the real API and creates/edits a real (then archived) issue.

Usage:
    LINEAR_API_KEY=lin_api_... uv run python scripts/smoke_test.py

Optional environment variables:
    LINEAR_TEAM_ID    UUID of the team to create the test issue in (default: first team).

Exit code is non-zero if any check fails.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from typing import Any

from linear_python_client import (
    CommentCreateRequest,
    CommentRequest,
    CommentsRequest,
    FindLabelRequest,
    FindProjectRequest,
    FindTeamRequest,
    FindUserRequest,
    FindWorkflowStateRequest,
    IssueAddLabelRequest,
    IssueArchiveRequest,
    IssueCreateRequest,
    IssueLabelsRequest,
    IssueRemoveLabelRequest,
    IssueRequest,
    IssueSetStateRequest,
    IssuesRequest,
    IssueUpdateRequest,
    LinearClient,
    ProjectRequest,
    ProjectsRequest,
    TeamRequest,
    TeamsRequest,
    UserRequest,
    UsersRequest,
    WorkflowStatesRequest,
)
from linear_python_client.graphql import queries

MARKER = "[linear-python-client smoke test]"


class Results:
    """Tallies pass/fail/skip checks and prints them as they happen."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        mark = "✓" if ok else "✗"
        suffix = f" — {detail}" if detail else ""
        print(f"  {mark} {label}{suffix}")
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        return ok

    def skip(self, label: str, why: str) -> None:
        print(f"  – SKIP {label} — {why}")
        self.skipped += 1

    def run(self, label: str, fn: Callable[[], Any]) -> Any:
        """Run a read-only call, reporting success/failure and returning its result."""
        try:
            value = fn()
        except Exception as exc:  # noqa: BLE001 - smoke test: report and continue
            self.check(label, False, f"raised {type(exc).__name__}: {exc}")
            return None
        self.check(label, True)
        return value


def section(title: str) -> None:
    print(f"\n== {title} ==")


def main() -> int:
    if not os.environ.get("LINEAR_API_KEY"):
        print("LINEAR_API_KEY is not set. Export a personal API key and re-run.")
        return 2

    r = Results()

    with LinearClient() as client:
        # -- read-only endpoints --------------------------------------------
        section("Read-only endpoints")

        viewer = r.run("viewer()", lambda: client.viewer().viewer)
        if viewer:
            r.check("viewer has id/name", bool(viewer.id and viewer.name), viewer.name)
            user = r.run("user(viewer.id)", lambda: client.user(UserRequest(id=viewer.id)).user)
            r.check("user() matches viewer", bool(user and user.id == viewer.id))

        r.run("users()", lambda: client.users(UsersRequest(first=5)).nodes)

        teams = r.run("teams()", lambda: client.teams(TeamsRequest(first=50)).nodes) or []
        r.check("at least one team exists", bool(teams))
        if not teams:
            print("\nNo teams available; cannot run issue checks.")
            return _summary(r)

        # LINEAR_TEAM_ID may be a UUID or a team key (e.g. "RAV"); team() resolves
        # both, but filters and mutations need the canonical UUID, so use team.id.
        team_ref = os.environ.get("LINEAR_TEAM_ID") or teams[0].id
        team = r.run(f"team(id={team_ref})", lambda: client.team(TeamRequest(id=team_ref)).team)
        if not team:
            print(f"\nCould not resolve team {team_ref!r}; cannot run issue checks.")
            return _summary(r)
        team_id = team.id
        print(f"  using team: {team.key} ({team_id})")

        states = (
            r.run(
                "workflow_states(team)",
                lambda: client.workflow_states(WorkflowStatesRequest(team_id=team_id)).nodes,
            )
            or []
        )
        r.check("team has workflow states", bool(states))

        r.run("issue_labels()", lambda: client.issue_labels(IssueLabelsRequest(first=50)).nodes)

        projects = (
            r.run("projects()", lambda: client.projects(ProjectsRequest(first=5)).nodes) or []
        )
        if projects:
            r.run(
                "project(id)",
                lambda: client.project(ProjectRequest(id=projects[0].id)).project,
            )
        else:
            r.skip("project(id)", "no projects in workspace")

        # raw GraphQL escape hatch
        data = r.run("execute(raw viewer query)", lambda: client.execute(queries.VIEWER))
        r.check("execute() returned viewer data", bool(data and data.get("viewer")))

        # paginate
        count = 0
        try:
            for _ in client.paginate(client.issues, IssuesRequest(first=2), page_size=2):
                count += 1
                if count >= 5:
                    break
            r.check("paginate(issues)", True, f"iterated {count} issue(s)")
        except Exception as exc:  # noqa: BLE001
            r.check("paginate(issues)", False, f"raised {type(exc).__name__}: {exc}")

        # -- name/key resolvers ---------------------------------------------
        section("Resolvers (name/key -> entity)")
        resolved_team = r.run(
            "find_team(by key)",
            lambda: client.find_team(FindTeamRequest(key=team.key)).team,
        )
        r.check(
            "find_team resolves to same id",
            bool(resolved_team and resolved_team.id == team_id),
        )
        if viewer and viewer.name:
            found_user = r.run(
                "find_user(by name)",
                lambda: client.find_user(FindUserRequest(name=viewer.name)).user,
            )
            r.check("find_user resolves to a user", bool(found_user and found_user.id))
        if projects:
            r.run(
                "find_project(by name)",
                lambda: client.find_project(FindProjectRequest(name=projects[0].name)).project,
            )
        else:
            r.skip("find_project()", "no projects in workspace")

        # -- create + verify ------------------------------------------------
        section("Create issue (+ pull to verify)")
        title = f"{MARKER} {int(time.time())}"
        created = r.run(
            "create_issue()",
            lambda: client.create_issue(
                IssueCreateRequest(
                    team_id=team_id, title=title, description="created by smoke test"
                )
            ),
        )
        if not (created and created.success and created.issue):
            r.check("create_issue succeeded", False)
            return _summary(r)
        issue_id = created.issue.id
        print(f"  created issue: {created.issue.identifier} ({issue_id})")

        def pull():
            return client.issue(IssueRequest(id=issue_id)).issue

        pulled = pull()
        r.check("pull: title matches", bool(pulled and pulled.title == title), title)

        try:
            # -- update + verify -------------------------------------------
            section("update_issue (+ pull to verify)")
            new_title = f"{title} (updated)"
            r.run(
                "update_issue()",
                lambda: client.update_issue(
                    IssueUpdateRequest(id=issue_id, title=new_title, priority=3)
                ),
            )
            pulled = pull()
            r.check("pull: title updated", bool(pulled and pulled.title == new_title))
            r.check("pull: priority updated", bool(pulled and pulled.priority == 3))

            # -- set status + verify ---------------------------------------
            section("set_issue_state + find_workflow_state (+ pull to verify)")
            current_state_id = pulled.state.id if pulled and pulled.state else None
            target = next((s for s in states if s.id != current_state_id), None)
            if target:
                r.run(
                    "set_issue_state()",
                    lambda: client.set_issue_state(
                        IssueSetStateRequest(id=issue_id, state_id=target.id)
                    ),
                )
                pulled = pull()
                r.check(
                    "pull: state updated",
                    bool(pulled and pulled.state and pulled.state.id == target.id),
                    target.name,
                )
                resolved = r.run(
                    "find_workflow_state(by name)",
                    lambda: client.find_workflow_state(
                        FindWorkflowStateRequest(team_id=team_id, name=target.name)
                    ).state,
                )
                r.check(
                    "find_workflow_state resolves to same id",
                    bool(resolved and resolved.id == target.id),
                )
            else:
                r.skip("set_issue_state()", "no alternative workflow state to switch to")

            # -- add / remove label + verify -------------------------------
            section("add_label / remove_label (+ pull to verify)")
            # A workspace may scope labels per team; a label from another team is
            # rejected ("labelIds for incorrect team"), so pick one for THIS team.
            team_labels = (
                r.run(
                    "issue_labels(team-scoped)",
                    lambda: client.issue_labels(
                        IssueLabelsRequest(filter={"team": {"id": {"eq": team_id}}}, first=50)
                    ).nodes,
                )
                or []
            )
            if team_labels:
                label = team_labels[0]
                resolved_label = r.run(
                    "find_label(by name)",
                    lambda: client.find_label(
                        FindLabelRequest(name=label.name, team_id=team_id)
                    ).label,
                )
                r.check("find_label resolves a label", bool(resolved_label and resolved_label.id))
                r.run(
                    "add_label()",
                    lambda: client.add_label(
                        IssueAddLabelRequest(id=issue_id, label_id=label.id)
                    ),
                )
                pulled = pull()
                r.check(
                    "pull: label present",
                    bool(pulled and any(lbl.id == label.id for lbl in pulled.labels)),
                    label.name,
                )
                r.run(
                    "remove_label()",
                    lambda: client.remove_label(
                        IssueRemoveLabelRequest(id=issue_id, label_id=label.id)
                    ),
                )
                pulled = pull()
                r.check(
                    "pull: label removed",
                    bool(pulled is not None and all(lbl.id != label.id for lbl in pulled.labels)),
                )
            else:
                r.skip("add_label()/remove_label()", f"team {team.key} has no team-scoped labels")

            # -- comment + verify ------------------------------------------
            section("create_comment (+ pull to verify)")
            body = f"{MARKER} comment {int(time.time())}"
            created_comment = r.run(
                "create_comment()",
                lambda: client.create_comment(
                    CommentCreateRequest(issue_id=issue_id, body=body)
                ),
            )
            comment_id = (
                created_comment.comment.id
                if created_comment and created_comment.comment
                else None
            )
            listed = r.run(
                "comments(issue_id=...)",
                lambda: client.comments(CommentsRequest(issue_id=issue_id)).nodes,
            )
            r.check(
                "pull: comment present in issue comments",
                bool(listed and any(c.body == body for c in listed)),
            )
            if comment_id:
                fetched = r.run(
                    "comment(id)",
                    lambda: client.comment(CommentRequest(id=comment_id)).comment,
                )
                r.check("pull: comment(id) body matches", bool(fetched and fetched.body == body))

            # -- full details ----------------------------------------------
            section("issue_details (full pull)")
            detail = r.run(
                "issue_details()",
                lambda: client.issue_details(IssueRequest(id=issue_id)).issue,
            )
            if detail:
                r.check("details: identifier present", bool(detail.identifier))
                r.check(
                    "details: includes the comment",
                    any(c.body == body for c in detail.comments),
                )
                r.check("details: state present", bool(detail.state))
        finally:
            # -- archive (cleanup) + verify --------------------------------
            section("archive_issue (cleanup)")
            archived = r.run(
                "archive_issue()",
                lambda: client.archive_issue(IssueArchiveRequest(id=issue_id)),
            )
            r.check("archive succeeded", bool(archived and archived.success))

    return _summary(r)


def _summary(r: Results) -> int:
    print(f"\n{'=' * 40}")
    print(f"PASSED {r.passed}  FAILED {r.failed}  SKIPPED {r.skipped}")
    return 1 if r.failed else 0


if __name__ == "__main__":
    sys.exit(main())
