"""One-turn process runner. Use a real OS/container sandbox in production."""
from __future__ import annotations
import json, os, shutil, signal, subprocess, sys, time
from dataclasses import dataclass
from pathlib import Path

MAX_OUTPUT = 64 * 1024
@dataclass
class BotError(Exception):
    code: str
    message: str
    stderr: str = ""

class BotRunner:
    def __init__(self, source, workdir, timeout=2.0):
        self.source, self.workdir, self.timeout = Path(source).resolve(), Path(workdir).resolve(), timeout
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.language = self.source.suffix.lower()
        if self.language not in (".py", ".cpp"): raise BotError("unsupported_language", "Chỉ hỗ trợ .py và .cpp")
        self.command = self._prepare()
    def _prepare(self):
        if self.language == ".py": return [sys.executable, str(self.source)]
        compiler = shutil.which("g++")
        if not compiler: raise BotError("compiler_unavailable", "Không tìm thấy g++")
        output = self.workdir / "bot-bin"
        p = subprocess.run([compiler, "-std=c++17", "-O2", str(self.source), "-o", str(output)], capture_output=True, text=True, timeout=15, cwd=self.workdir)
        if p.returncode: raise BotError("compile_error", "Biên dịch C++ thất bại", p.stderr[:4096])
        return [str(output)]
    def run_turn(self, state):
        started = time.monotonic()
        def limit_resources():
            # Linux-only defence in depth. Public deployments still need an isolated worker/container.
            try:
                import resource
                resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
                resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT, MAX_OUTPUT))
                resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
                resource.setrlimit(resource.RLIMIT_CPU, (max(1, int(self.timeout) + 1), max(2, int(self.timeout) + 2)))
            except (ImportError, ValueError):
                pass
        try:
            p = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, cwd=self.workdir, start_new_session=True,
                                 preexec_fn=limit_resources if os.name == "posix" else None)
            stdout, stderr = p.communicate(json.dumps(state), timeout=self.timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL) if os.name == "posix" else p.kill()
            _, stderr = p.communicate()
            raise BotError("timeout", "Bot quá thời gian", stderr[:4096])
        elapsed = round((time.monotonic() - started) * 1000)
        if p.returncode: raise BotError("crash", f"Bot kết thúc với mã {p.returncode}", stderr[:4096])
        if len(stdout.encode()) > MAX_OUTPUT: raise BotError("output_too_large", "stdout vượt giới hạn", stderr[:4096])
        try: output = json.loads(stdout)
        except json.JSONDecodeError: raise BotError("invalid_json", "stdout không phải một JSON hợp lệ", stderr[:4096])
        if not isinstance(output, dict) or "move" not in output or not isinstance(output["move"], dict): raise BotError("invalid_schema", "Output phải có move object", stderr[:4096])
        if any(k not in output["move"] for k in ("piece_id", "from", "to")): raise BotError("invalid_schema", "move thiếu piece_id/from/to", stderr[:4096])
        try: json.dumps(output.get("userdata"))
        except (TypeError, ValueError): raise BotError("invalid_schema", "userdata phải JSON-serializable", p.stderr[:4096])
        if len(json.dumps(output.get("userdata")).encode()) > 4096: raise BotError("userdata_too_large", "userdata vượt 4KB", p.stderr[:4096])
        return output, {"elapsed_ms": elapsed, "stderr": stderr[:4096], "exit_code": p.returncode}
