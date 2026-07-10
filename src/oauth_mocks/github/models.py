"""Response models for the GitHub mock."""

from pydantic import BaseModel


class GitHubUser(BaseModel):
    """GitHub user profile response."""

    id: int
    login: str
    name: str | None
    email: str | None
    avatar_url: str
    html_url: str
    type: str = "User"
    site_admin: bool = False
    company: str | None = None
    blog: str | None = None
    location: str | None = None
    bio: str | None = None
    twitter_username: str | None = None
    public_repos: int = 0
    public_gists: int = 0
    followers: int = 0
    following: int = 0
    created_at: str = "2020-01-01T00:00:00Z"
    updated_at: str = "2024-01-01T00:00:00Z"


class GitHubEmail(BaseModel):
    """GitHub email response."""

    email: str
    primary: bool
    verified: bool
    visibility: str | None = "private"


class GitHubInstallationAccount(BaseModel):
    """GitHub installation account."""

    login: str
    type: str


class GitHubInstallation(BaseModel):
    """GitHub App installation."""

    id: int
    account: GitHubInstallationAccount


class GitHubInstallationsResponse(BaseModel):
    """GitHub App installations response."""

    installations: list[GitHubInstallation]


class GitHubRepositoryOwner(BaseModel):
    """GitHub repository owner."""

    login: str


class GitHubRepository(BaseModel):
    """GitHub repository response."""

    id: int
    name: str
    full_name: str
    private: bool
    owner: GitHubRepositoryOwner
    default_branch: str = "main"
    updated_at: str = "2024-01-01T00:00:00Z"


class GitHubCommitData(BaseModel):
    """GitHub commit inner data."""

    message: str


class GitHubCommit(BaseModel):
    """GitHub commit response."""

    sha: str
    commit: GitHubCommitData


class GitHubInstallationRepositoriesResponse(BaseModel):
    """GitHub installation repositories response."""

    total_count: int
    repositories: list[GitHubRepository]
