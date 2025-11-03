# Quick Commands - Copy & Paste

## 🚀 Start Server (Terminal 1)

```bash
cd /Users/george/ECE461_Team17/ECE461_Team17_Phase2
export GITHUB_TOKEN="your_token_here"
cd src
python3 app.py
```

---

## 📸 Deliverable 1: Upload Package (Terminal 2)

```bash
cd /Users/george/ECE461_Team17/ECE461_Team17_Phase2

curl -X POST http://127.0.0.1:8080/package \
  -H "Content-Type: application/json" \
  -d '{
    "name": "bert-base-uncased",
    "version": "1.0.0",
    "url": "https://huggingface.co/bert-base-uncased"
  }' | python3 -m json.tool
```

**📸 Screenshot this!**
**⚠️ Copy the `package_id` from the response!**

---

## 📸 Deliverable 2: Retrieve Package (Terminal 2)

```bash
# Replace YOUR_PACKAGE_ID with the ID from step above
curl http://127.0.0.1:8080/package/YOUR_PACKAGE_ID | python3 -m json.tool
```

**📸 Screenshot this!**

---

## ⚡ If Flask Not Installed

```bash
pip3 install Flask
```

---

## ✅ Verify It Works

```bash
# Test API is running
curl http://127.0.0.1:8080/

# Check storage
ls -la package_storage/metadata/
```

---

## 📝 Notes Templates

### Deliverable 1:
```
✅ Works: Upload endpoint, unique IDs, all 8 metrics, net score, storage
⚠️ Limited: File storage (not DB), simple IDs, only URL upload
❌ Missing: Content upload, database, auth, versioning
```

### Deliverable 2:
```
Endpoint: GET /package/{id}
✅ Why: Simplest, proves persistence, required for verification, RESTful
✅ Implements: ID lookup, all metadata, proper status codes, fast
⚠️ Missing: Search filters, pagination, field selection
```

---

**See `MVP_TESTING_GUIDE.md` for full details**

