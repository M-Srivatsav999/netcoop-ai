# Steps to Create Fresh GitHub Repo

Run these commands **in your terminal (not VS Code terminal if it's locked)**:

```powershell
# 1. Go to your project
cd c:\Users\mukka\Documents\antigravity\lucid-hawking

# 2. Delete old git history (run as normal user in PowerShell)
Remove-Item -Recurse -Force .git

# 3. Initialize fresh repo
git init
git branch -M main

# 4. Stage all NetCoop files (gitignore will exclude GapFinder leftovers)
git add .

# 5. First clean commit
git commit -m "feat: NetCoop AI - deterministic multi-agent campus network fault diagnosis"

# 6. Go to github.com → New Repository
#    Name it: netcoop-ai
#    Set to PUBLIC
#    Do NOT add README/gitignore (we have our own)

# 7. Add your new remote (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/netcoop-ai.git

# 8. Push
git push -u origin main
```

## After pushing, verify:
- Repo name shows "netcoop-ai" not "gapfinder-ai"
- No app/, components/, lib/, prisma/ folders visible on GitHub
- No .env file visible
- README.md shows NetCoop AI content
