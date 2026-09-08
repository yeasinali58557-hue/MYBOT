- name: Commit and Push Database
        if: always()
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action Bot"
          git add bot_data.db
          git diff --quiet && git diff --staged --quiet || (git commit -m "Auto-update database [skip ci]" && git push https://${{ secrets.GH_TOKEN }}@github.com/${{ github.repository }}.git HEAD:main)
