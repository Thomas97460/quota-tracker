import os
import pty
import select
import subprocess
import time
import re

def strip_ansi(text: str) -> str:
    ansi = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    return ansi.sub("", text).replace("\r", "\n")

def debug_gemini():
    cmd = ["gemini", "--skip-trust", "-m", "gemini-3-flash-preview"]
    master_fd, slave_fd = pty.openpty()
    process = subprocess.Popen(
        cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)

    start = time.monotonic()
    raw_chunks = []
    sent_stats = False
    sent_exit = False
    
    print("--- STARTING CAPTURE ---")
    while (time.monotonic() - start) < 30:
        if process.poll() is not None:
            print("Process exited")
            break

        ready, _, _ = select.select([master_fd], [], [], 0.1)
        if ready:
            chunk = os.read(master_fd, 8192)
            if not chunk:
                break
            raw_chunks.append(chunk)
            text = strip_ansi(b"".join(raw_chunks).decode("utf-8", errors="replace"))
            
            # Print new chunks for debugging
            # print(f"DEBUG: {repr(chunk.decode('utf-8', errors='replace'))}")

            if not sent_stats and ("Type your message" in text or "Ready (" in text):
                print("Sending /stats model")
                os.write(master_fd, b"/stats model\n")
                sent_stats = True

            if sent_stats and not sent_exit and ("Model Usage Statistics" in text or "No API calls" in text):
                print("Captured stats, exiting")
                os.write(master_fd, b"/exit\n")
                sent_exit = True
                break

    full_text = strip_ansi(b"".join(raw_chunks).decode("utf-8", errors="replace"))
    print("--- FULL CAPTURED TEXT ---")
    print(full_text)
    print("--- END ---")

if __name__ == "__main__":
    debug_gemini()
