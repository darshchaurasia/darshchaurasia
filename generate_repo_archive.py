import os
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()

HEADERS = {'authorization': 'token ' + os.environ['ACCESS_TOKEN']}
USER_NAME = os.environ['USER_NAME']
ARCHIVE_FILE = 'cache/repository_archive.txt'


def hash_repo_name(name_with_owner):
    """Generates a SHA-256 hash for a repository name."""
    return hashlib.sha256(name_with_owner.encode('utf-8')).hexdigest()


def fetch_contributed_repos(username, after_cursor=None):
    """Fetches all repositories a user has contributed to."""
    query = '''
    query($login: String!, $cursor: String) {
        user(login: $login) {
            repositoriesContributedTo(first: 100, after: $cursor) {
                edges {
                    node {
                        nameWithOwner
                        defaultBranchRef {
                            target {
                                ... on Commit {
                                    history {
                                        totalCount
                                    }
                                }
                            }
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }
    '''
    variables = {'login': username, 'cursor': after_cursor}
    response = requests.post('https://api.github.com/graphql', json={'query': query, 'variables': variables}, headers=HEADERS)
    response.raise_for_status()
    data = response.json()['data']['user']['repositoriesContributedTo']
    return data['edges'], data['pageInfo']


def fetch_actual_loc(owner, repo_name):
    """Fetches actual lines added and deleted by the user for a given repository."""
    additions, deletions, my_commits = 0, 0, 0
    cursor = None
    while True:
        query = '''
        query($owner: String!, $repo: String!, $cursor: String) {
            repository(owner: $owner, name: $repo) {
                defaultBranchRef {
                    target {
                        ... on Commit {
                            history(first: 100, after: $cursor) {
                                edges {
                                    node {
                                        author {
                                            user {
                                                login
                                            }
                                        }
                                        additions
                                        deletions
                                    }
                                }
                                pageInfo {
                                    endCursor
                                    hasNextPage
                                }
                            }
                        }
                    }
                }
            }
        }
        '''
        variables = {'owner': owner, 'repo': repo_name, 'cursor': cursor}
        response = requests.post('https://api.github.com/graphql', json={'query': query, 'variables': variables}, headers=HEADERS)
        response.raise_for_status()
        history = response.json()['data']['repository']['defaultBranchRef']['target']['history']

        for commit in history['edges']:
            if commit['node']['author']['user'] and commit['node']['author']['user']['login'] == USER_NAME:
                my_commits += 1
                additions += commit['node']['additions']
                deletions += commit['node']['deletions']

        if not history['pageInfo']['hasNextPage']:
            break
        cursor = history['pageInfo']['endCursor']

    return my_commits, additions, deletions


def generate_archive(username):
    print(f"🔄 Generating archive for user: {username}...")
    with open(ARCHIVE_FILE, 'w') as f:
        # Write header in the exact same format
        f.write("This is an archive of all of the deleted repositories I have contributed to.\n\n")
        f.write("repository (hashed)  total commits  my commits  LOC added by me  LOC deleted by me\n")
        f.write("         \\                \\                \\           \\___________  \\\n")
        f.write("          \\                \\                \\_____________________ \\  \\\n")
        f.write("           \\                \\___________________________________  \\ \\  \\\n")
        f.write("____________\\___________________________________________________\\__\\_\\__\\____\n")

        cursor = None
        while True:
            repos, page_info = fetch_contributed_repos(username, cursor)
            for repo in repos:
                try:
                    name_with_owner = repo['node']['nameWithOwner']
                    owner, repo_name = name_with_owner.split('/')
                    repo_hash = hash_repo_name(name_with_owner)
                    total_commits = repo['node']['defaultBranchRef']['target']['history']['totalCount']
                    my_commits, additions, deletions = fetch_actual_loc(owner, repo_name)
                    # Only write repos with actual contributions
                    if my_commits > 0 or additions > 0 or deletions > 0:
                        f.write(f"{repo_hash} {total_commits} {my_commits} {additions} {deletions}\n")
                except (TypeError, KeyError) as e:
                    print(f"⚠️  Skipping {name_with_owner} - no commit history available")

            if not page_info['hasNextPage']:
                break
            cursor = page_info['endCursor']

    print("✅ Archive generation complete.")


generate_archive(USER_NAME)
