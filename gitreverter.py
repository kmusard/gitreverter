import datetime
import argparse
from collections import OrderedDict
from pygit2 import Repository, Signature


class GitReverter:
    def __init__(self, repo_path, ref, commit_hash):
        self.repo = Repository(repo_path)
        self.ref = None
        self.commit_hash = None
        self.head = None
        self.tmp_branch = None
        self.target_commits = OrderedDict()
        self.repo.checkout("refs/heads/{0}".format(ref))
        for commit in self.repo.walk(self.repo.head.target):
            if str(commit.id).startswith(commit_hash):
                self.commit_hash = commit_hash
                self.ref = ref
                break
        if self.commit_hash is None:
            raise RuntimeError(
                "Commit hash {0} not found on ref {1}".format(commit_hash, ref)
            )

    def setup_tmp_branch(self):
        """
        Create temporary branch from the ref, and set repo head to it
        """
        now = datetime.datetime.now()
        branch = "git_reverter_{0}".format(now.strftime("%Y-%m-%d-%H%M%S"))
        self.repo.checkout("refs/heads/{0}".format(self.ref))
        head = next(iter(self.repo.walk(self.repo.head.target)))
        tmp_branch = self.repo.branches.local.create(branch, head)
        self.repo.checkout("refs/heads/{0}".format(tmp_branch.branch_name))
        self.tmp_branch = tmp_branch.branch_name
        self.head = next(iter(self.repo.walk(self.repo.head.target)))

    def test_all_single_revert(self):
        """
        Check if each commit can be reverted on its own
        """
        self.setup_tmp_branch()
        for commit in self.repo.walk(self.repo.head.target):
            index = self.repo.revert_commit(commit, self.head)
            if index.conflicts:
                self.target_commits[commit] = True
            else:
                self.target_commits[commit] = False
        self.repo.checkout("refs/heads/{0}".format(self.ref))
        self.repo.branches.local.delete(self.tmp_branch)
        return self.target_commits

    def revert_all_reverse(self):
        """
        Revert all commits in reverse order, up to the target commit
        """
        self.setup_tmp_branch()
        for commit in self.repo.walk(self.repo.head.target):
            message = "Revert {0}".format(commit.message)
            new_head = next(iter(self.repo.walk(self.repo.head.target)))
            self.repo.revert_commit(commit, new_head)
            index = self.repo.index
            if index.conflicts:
                raise RuntimeError(
                    "Commit {0} cannot be reverted due to conflicts".format(commit.id)
                )
            index.add_all()
            index.write()
            tree = index.write_tree()
            curr_ref = self.repo.head.name
            parents = [self.repo.head.target]
            signature = Signature(
                self.repo.config["user.name"], self.repo.config["user.email"]
            )
            self.repo.create_commit(
                curr_ref,
                signature,
                signature,
                message,
                tree,
                parents,
            )

    def cleanup_branches(self):
        """
        Delete all temporary branches
        """
        for branch in self.repo.branches.local:
            if branch.startswith("git_reverter_"):
                self.repo.branches.local.delete(branch)


def setup_args():
    """
    Setup command line arguments
    """
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    parser.add_argument(
        "--path",
        type=str,
        required=True,
        help="Path to local git repository",
    )
    parser.add_argument(
        "--ref",
        type=str,
        required=True,
        help="Target ref (branch or tag)",
    )
    parser.add_argument(
        "--commit",
        type=str,
        required=True,
        help="Target commit hash",
    )
    group.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze existence of conflicts when individually reverting each commit, "
        + "up to and including the target commit",
    )
    group.add_argument(
        "--revert",
        action="store_true",
        help="Revert the all commits, up to and including the target commit",
    )
    group.add_argument(
        "--cleanup",
        action="store_true",
        help="Cleanup git_reverter_* temporary branches",
    )
    return parser.parse_args()


def main():
    args = setup_args()
    reverter = GitReverter(args.path, args.ref, args.commit)
    if args.analyze:
        header = "{0:8s} {1:10s} {2:20s} {3:20s} {4:50s}".format(
            "Commit", "Conflicts", "Author", "Time", "Message"
        )
        print(header)
        results = reverter.test_all_single_revert()
        for commit, conflicts in results.items():
            commit_time = datetime.datetime.fromtimestamp(commit.commit_time)
            print(
                "{0:8s} {1:10s} {2:20s} {3:20s} {4:50s}".format(
                    commit.short_id,
                    str(conflicts),
                    commit.author.name,
                    commit_time.strftime("%Y-%m-%d %H:%M:%S"),
                    str.strip(commit.message),
                )
            )
    elif args.revert:
        reverter.revert_all_reverse()
    elif args.cleanup:
        reverter.cleanup_branches()


if __name__ == "__main__":
    main()
