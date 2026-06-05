"""GraphQL query and mutation strings used by :class:`linear_python.client.LinearClient`.

Field selections are factored into reusable fragments so the operations below stay
readable and the requested fields line up with the dataclasses in ``models.py``.
"""

from __future__ import annotations

# --- Field fragments -------------------------------------------------------

USER_FIELDS = """
fragment UserFields on User {
  id
  name
  displayName
  email
  active
  admin
  createdAt
}
"""

TEAM_FIELDS = """
fragment TeamFields on Team {
  id
  name
  key
  description
  private
  createdAt
}
"""

STATE_FIELDS = """
fragment StateFields on WorkflowState {
  id
  name
  type
  color
  position
}
"""

LABEL_FIELDS = """
fragment LabelFields on IssueLabel {
  id
  name
  color
}
"""

PROJECT_FIELDS = """
fragment ProjectFields on Project {
  id
  name
  description
  slugId
  state
  progress
  createdAt
}
"""

COMMENT_FIELDS = """
fragment CommentFields on Comment {
  id
  body
  url
  createdAt
  updatedAt
  user { ...UserFields }
}
"""

ISSUE_FIELDS = """
fragment IssueFields on Issue {
  id
  identifier
  title
  description
  url
  priority
  estimate
  branchName
  createdAt
  updatedAt
  completedAt
  assignee { ...UserFields }
  creator { ...UserFields }
  team { ...TeamFields }
  state { ...StateFields }
  labels { nodes { ...LabelFields } }
}
"""


def _compose(*parts: str) -> str:
    """Join an operation body with the fragments it depends on."""
    return "\n".join(part.strip() for part in parts)


# --- Queries ---------------------------------------------------------------

VIEWER = _compose(
    USER_FIELDS,
    """
query Viewer {
  viewer { ...UserFields }
}
""",
)

USER = _compose(
    USER_FIELDS,
    """
query User($id: String!) {
  user(id: $id) { ...UserFields }
}
""",
)

USERS = _compose(
    USER_FIELDS,
    """
query Users($first: Int, $after: String, $filter: UserFilter) {
  users(first: $first, after: $after, filter: $filter) {
    nodes { ...UserFields }
    pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
  }
}
""",
)

TEAM = _compose(
    TEAM_FIELDS,
    """
query Team($id: String!) {
  team(id: $id) { ...TeamFields }
}
""",
)

TEAMS = _compose(
    TEAM_FIELDS,
    """
query Teams($first: Int, $after: String, $filter: TeamFilter) {
  teams(first: $first, after: $after, filter: $filter) {
    nodes { ...TeamFields }
    pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
  }
}
""",
)

ISSUE = _compose(
    ISSUE_FIELDS,
    USER_FIELDS,
    TEAM_FIELDS,
    STATE_FIELDS,
    LABEL_FIELDS,
    """
query Issue($id: String!) {
  issue(id: $id) { ...IssueFields }
}
""",
)

ISSUES = _compose(
    ISSUE_FIELDS,
    USER_FIELDS,
    TEAM_FIELDS,
    STATE_FIELDS,
    LABEL_FIELDS,
    """
query Issues($first: Int, $after: String, $filter: IssueFilter, $orderBy: PaginationOrderBy) {
  issues(first: $first, after: $after, filter: $filter, orderBy: $orderBy) {
    nodes { ...IssueFields }
    pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
  }
}
""",
)

PROJECT = _compose(
    PROJECT_FIELDS,
    """
query Project($id: String!) {
  project(id: $id) { ...ProjectFields }
}
""",
)

PROJECTS = _compose(
    PROJECT_FIELDS,
    """
query Projects($first: Int, $after: String, $filter: ProjectFilter) {
  projects(first: $first, after: $after, filter: $filter) {
    nodes { ...ProjectFields }
    pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
  }
}
""",
)

COMMENT = _compose(
    COMMENT_FIELDS,
    USER_FIELDS,
    """
query Comment($id: String!) {
  comment(id: $id) { ...CommentFields }
}
""",
)

COMMENTS = _compose(
    COMMENT_FIELDS,
    USER_FIELDS,
    """
query Comments($first: Int, $after: String, $filter: CommentFilter) {
  comments(first: $first, after: $after, filter: $filter) {
    nodes { ...CommentFields }
    pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
  }
}
""",
)

WORKFLOW_STATES = _compose(
    STATE_FIELDS,
    """
query WorkflowStates($first: Int, $after: String, $filter: WorkflowStateFilter) {
  workflowStates(first: $first, after: $after, filter: $filter) {
    nodes { ...StateFields }
    pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
  }
}
""",
)

ISSUE_LABELS = _compose(
    LABEL_FIELDS,
    """
query IssueLabels($first: Int, $after: String, $filter: IssueLabelFilter) {
  issueLabels(first: $first, after: $after, filter: $filter) {
    nodes { ...LabelFields }
    pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
  }
}
""",
)


# --- Mutations -------------------------------------------------------------

ISSUE_CREATE = _compose(
    ISSUE_FIELDS,
    USER_FIELDS,
    TEAM_FIELDS,
    STATE_FIELDS,
    LABEL_FIELDS,
    """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { ...IssueFields }
  }
}
""",
)

ISSUE_UPDATE = _compose(
    ISSUE_FIELDS,
    USER_FIELDS,
    TEAM_FIELDS,
    STATE_FIELDS,
    LABEL_FIELDS,
    """
mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { ...IssueFields }
  }
}
""",
)

ISSUE_ARCHIVE = """
mutation IssueArchive($id: String!) {
  issueArchive(id: $id) {
    success
  }
}
""".strip()

COMMENT_CREATE = _compose(
    COMMENT_FIELDS,
    USER_FIELDS,
    """
mutation CommentCreate($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment { ...CommentFields }
  }
}
""",
)
