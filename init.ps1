git fetch
git checkout release-candidate
git merge origin/main --allow-unrelated-histories
git push
git checkout dev
git merge origin/main --allow-unrelated-histories
git push
