## 每日執行規則

- 時區：台灣時間（UTC+8）
- 每日指定時間點：08:00
- 觸發方式：GitHub Actions（`.github/workflows/daily-ranking.yml`）排程自動執行，或手動觸發

## 每日排名格式

依每日排名資料，產製一個 JSON 檔，存放於 `data/YYYY-MM-DD.json`：

```json
{
  "date": "YYYY-MM-DD",
  "source": "Claude AI WebSearch",
  "rankings": [
    {
      "rank": 1,
      "name": "品牌名稱",
      "score": 12345,
      "change": "same",
      "trend_label": "穩居冠軍",
      "tags": ["標籤A", "標籤B", "標籤C"],
      "desc": "品牌簡介（50 字以內）"
    }
  ]
}
```

`change` 欄位值：`up`、`down`、`same`、`new`

## 每日 index.html 更新規則

每次新增排名時，步驟如下：

1. 把目前最上方的 `<div class="date-divider latest">` 改為 `<div class="date-divider">`（移除 latest）
2. 在 `</header>` 之後，原第一個 date-divider 之前，插入新日期區塊：

```html
<!-- ══════════════════════════════════
     YYYY/MM/DD
══════════════════════════════════ -->
<div class="date-divider latest">
  <span class="date-label">YYYY / MM / DD</span>
</div>
<div class="feed">
  <!-- 5 張 card -->
</div>
```

3. 每張 card 結構：

```html
<div class="card">
  <div class="rank r{N}">{N}</div>
  <div class="avatar av{N}">{品牌短名}</div>
  <div>
    <div class="top-row">
      <span class="name">{品牌全名}</span>
      <span class="trend trend-{change}">{trend_label}</span>
    </div>
    <div class="tags">
      <span class="tag">{tag1}</span>
      <span class="tag">{tag2}</span>
      <span class="tag">{tag3}</span>
    </div>
    <div class="score-bar">
      <span class="score-label">聲量</span>
      <span class="score-num">{score 千分位} 則</span>
      <div class="bar-wrap"><div class="bar-fill" style="width:{score/rank1_score*100}%"></div></div>
    </div>
  </div>
  <p class="desc">{desc}</p>
</div>
```

- `r{N}` 與 `av{N}`：N = 1–5，對應排名（av1–av5 每次均可重複使用）
- `trend-{change}` 對應：up → `trend-up`、down → `trend-down`、same → `trend-same`、new → `trend-new`
- 聲量條寬度：`score ÷ 第1名score × 100`，第1名固定 100%

## Git 提交規則

```bash
git add data/YYYY-MM-DD.json index.html
git commit -m "Daily ranking YYYY-MM-DD"
git push origin claude/newsfeed-webpage-scraper-IENPA
```

> 永遠 push 到 `claude/newsfeed-webpage-scraper-IENPA`，不要 push 到 main。
