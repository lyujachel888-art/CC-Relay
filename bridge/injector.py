import subprocess


def inject_to_tmux(session: str, text: str) -> None:
    """Send text to a tmux session and press Enter.

    Uses `--` to terminate options so text starting with `-` is treated as literal.
    """
    subprocess.run(
        ["tmux", "send-keys", "-t", session, "--", text],
        check=True,
    )
    subprocess.run(
        ["tmux", "send-keys", "-t", session, "Enter"],
        check=True,
    )
