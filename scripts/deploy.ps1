# Build a city's site and put it on Cloudflare Pages: .\scripts\deploy.ps1 (Amersfoort) or .\scripts\deploy.ps1 utrecht
# --force sends the upload straight to Cloudflare Pages: without it wrangler 4.15x first looks for the project on
# Workers, does not find it there and offers to create a new one.
param([string]$City = "amersfoort")
python scripts/build_site.py $City
if ($LASTEXITCODE -eq 0) {
    npx wrangler pages deploy "dist/$City" --project-name "layrs-$City" --branch main --commit-dirty=true --force
}
