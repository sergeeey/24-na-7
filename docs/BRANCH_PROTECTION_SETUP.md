# Branch Protection Setup — Настройка защиты веток

Этот документ описывает настройку branch protection rules для GitHub репозитория Reflexio 24/7.

## Зачем нужна Branch Protection?

Branch protection предотвращает:
- ❌ Merge без прохождения PR gate checks (hallucination rate, coverage)
- ❌ Force push в main/master
- ❌ Прямые коммиты без review
- ❌ Деградацию качества кода

## Требуемые Settings (для main/master)

### 1. Require Pull Request Before Merging

Настройка: Settings → Branches → Branch protection rules → Add rule

**Branch name pattern:** `main` (или `master`)

#### Обязательные опции:

✅ **Require a pull request before merging**
- ✅ Require approvals: **1** (минимум)
- ✅ Dismiss stale pull request approvals when new commits are pushed
- ⬜ Require review from Code Owners (optional)

✅ **Require status checks to pass before merging**
- ✅ Require branches to be up to date before merging
- **Required status checks:**
  - `test` (все tests passing)
  - `pr-gates / PR Quality Gates` (hallucination rate, coverage, unit tests)

✅ **Require conversation resolution before merging**
- Все comments должны быть resolved

✅ **Require signed commits** (опционально, для compliance)

⬜ **Require linear history** (опционально, для чистоты истории)

✅ **Do not allow bypassing the above settings**
- Даже admins должны следовать rules

### 2. Restrict Force Pushes

✅ **Restrict pushes that delete matching branches** (никто не может удалить main)

❌ **Allow force pushes** → OFF (никто не может делать force push в main)

### 3. Allow Specific Actors (Optional)

Если нужно разрешить emergency push для specific users:
- Add admin users в exceptions
- Рекомендация: **не добавлять**, force через PR даже для admins

## Настройка через GitHub UI

### Шаг 1: Открыть Settings

```
Repository → Settings → Branches → Branch protection rules → Add rule
```

### Шаг 2: Создать Rule для main

1. **Branch name pattern:** `main`
2. Включить все опции выше
3. Click **Create** внизу страницы

### Шаг 3: Проверить Required Status Checks

В разделе "Require status checks to pass before merging":
1. Искать `test` и `pr-gates` в dropdown
2. Если не видны — запустить CI workflow хотя бы раз (push в PR)
3. Вернуться в settings и добавить

### Шаг 4: Test Protection Rules

Создать тестовый PR:
```bash
git checkout -b test-branch-protection
echo "test" > test.txt
git add test.txt
git commit -m "test: verify branch protection"
git push origin test-branch-protection
```

Открыть PR в GitHub → должны быть видны:
- ✅ Status checks (test, pr-gates)
- ⬜ Merge button disabled до прохождения checks

## Настройка через GitHub API (Automation)

Для автоматизации через API:

```bash
# Требуется GITHUB_TOKEN с permissions: repo
curl -X PUT \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/sergeeey/24-na-7/branches/main/protection \
  -d '{
    "required_status_checks": {
      "strict": true,
      "contexts": ["test", "pr-gates / PR Quality Gates"]
    },
    "enforce_admins": true,
    "required_pull_request_reviews": {
      "dismiss_stale_reviews": true,
      "require_code_owner_reviews": false,
      "required_approving_review_count": 1
    },
    "restrictions": null,
    "allow_force_pushes": false,
    "allow_deletions": false
  }'
```

## Проверка Current Settings

Проверить текущие branch protection rules:

```bash
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/sergeeey/24-na-7/branches/main/protection
```

## Troubleshooting

### Issue: "Required checks не видны в dropdown"

**Решение:**
1. Запустить CI workflow хотя бы раз (push в любой PR)
2. Wait for workflow completion
3. Вернуться в Settings → Branches → обновить страницу
4. Required checks появятся в dropdown

### Issue: "Merge blocked even though checks passed"

**Проверка:**
1. Все required status checks passing?
2. Branch up-to-date с main?
3. Все conversations resolved?
4. Required approvals получены?

**Решение:**
- Update branch from main: `git merge main` или "Update branch" button
- Resolve all conversations
- Request review если нет approvals

### Issue: "Admin bypass не работает"

**Причина:** "Do not allow bypassing" включен

**Решение:**
- Temporary disable rule
- Merge emergency fix
- Re-enable rule сразу после

## Best Practices

1. **Никогда не disable branch protection** — даже временно
2. **Не добавлять admins в exceptions** — force через PR
3. **Monitor failed checks** — если PR gates часто fail, улучшить тесты
4. **Regular review** — проверять rules каждые 3 месяца

## Integration с v4.1 PR Gates

После настройки branch protection, PR gates будут автоматически блокировать merge при:

| Check | Trigger | Action |
|-------|---------|--------|
| Hallucination Rate >0.5% | Golden set test fail | ❌ Block merge |
| Citation Coverage <98% | Golden set test fail | ❌ Block merge |
| Test Coverage <80% | pytest-cov fail | ❌ Block merge |
| Unit Tests failing | pytest fail | ❌ Block merge |

## Verification

После настройки проверить:

```bash
# 1. Создать тестовый PR с breaking change
echo "def broken(): pass" >> src/models/fact.py
git add src/models/fact.py
git commit -m "test: intentional break"
git push origin test-branch

# 2. Открыть PR → merge button должен быть disabled
# 3. Verify status checks появляются в PR
# 4. Revert change и close PR
```

---

**Готово!** Branch protection теперь защищает main от hallucinations и low coverage.
