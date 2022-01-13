from util.cmd_helper import CmdHelper as CLI


class Git:
    @staticmethod
    def add_all_and_commit(dir, msg):
        commit_command = f"""
        pushd {dir}
        if [ "$(git rev-parse --is-inside-work-tree 2>/dev/null)" != "true" ]; then
            echo "GIT NOT INITIALIZED"
            git init
        fi
        echo "Git changes"
        git status --porcelain
        git diff --exit-code
        echo "Adding user email"
        git config --global user.email "concourse@arcas.com"
        git add .
        git commit -m "{msg}"
        popd
        """
        CLI.execute_cmd(commit_command)
