# ⚡ Quick Commands - Search Endpoint

## 🚀 One-Line Setup
```bash
cd /Users/george/ECE461_Team17/ECE461_Team17_Phase2 && source venv/bin/activate && export GITHUB_TOKEN="your_token" && cd src && python3 app.py
```

---

## 📤 Upload Test Packages (Terminal 2)

```bash
# BERT base
curl -X POST http://127.0.0.1:8080/package -H "Content-Type: application/json" -d '{"name": "bert-base-uncased", "version": "1.0.0", "url": "https://huggingface.co/bert-base-uncased"}'

# BERT large
curl -X POST http://127.0.0.1:8080/package -H "Content-Type: application/json" -d '{"name": "bert-large-uncased", "version": "1.0.0", "url": "https://huggingface.co/bert-large-uncased"}'

# GPT-2
curl -X POST http://127.0.0.1:8080/package -H "Content-Type: application/json" -d '{"name": "gpt2", "version": "1.0.0", "url": "https://huggingface.co/gpt2"}'
```

---

## 📸 BEST FOR SCREENSHOT

```bash
curl "http://127.0.0.1:8080/packages/byRegex?RegEx=bert"
```

---

## 🎨 With Pretty Formatting

```bash
curl -s "http://127.0.0.1:8080/packages/byRegex?RegEx=bert" | jq
```

---

## 🔍 Other Search Options

```bash
# Advanced regex
curl "http://127.0.0.1:8080/packages/byRegex?RegEx=bert.*uncased"

# Prefix search
curl "http://127.0.0.1:8080/packages/byRegex?RegEx=^gpt"

# All packages (regex .*)
curl "http://127.0.0.1:8080/packages/byRegex?RegEx=.*"
```

---

## 📝 Screenshot Caption Template

```
Endpoint: GET /packages/byRegex?RegEx=bert

What Works:
✅ Regex pattern matching (case-insensitive)
✅ Sorted by net score (highest first)
✅ Multiple package results
✅ Full scoring integration

Why This Endpoint:
- Enables package discovery (better than /id)
- Shows advanced filtering with regex
- Demonstrates multi-package handling
- Production-ready query interface

Missing (MVP scope):
- Pagination, full-text search, caching
```

