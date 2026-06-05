# Models

The Pydantic entity models nested inside responses. Fields are snake_case with
camelCase aliases, and everything is optional, so only the fields a query actually
requested are populated.

::: linear_python.models.entities
    options:
      show_root_heading: false
      show_root_toc_entry: false
      members:
        - LinearModel
        - PageInfo
        - User
        - Team
        - Issue
        - Project
        - Comment
        - WorkflowState
        - IssueLabel
