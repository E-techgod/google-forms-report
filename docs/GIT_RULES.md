# Git Feature Workflow Rules

1. **Branch**: `git checkout -b feature/<name>` (isolate work)
2. **Test**: `uv run pytest -v` (automated + manual verification)
3. **Commit**: `git add . && git commit -m "feat: <summary>"`
4. **Push**: `git push -u origin feature/<name>`
5. **Open PR**: `gh pr create --title "<title>" --body "<body>"` (add `--base main` if needed)
   - If tests fail: `git add . && git commit -m "fix: <msg>" && git push`
6. **Merge**: On GitHub: **Squash and merge** → **Confirm** → **Delete branch**
7. **Sync & Cleanup**:
   ```bash
   git checkout main && git pull origin main && git branch -d feature/<name>