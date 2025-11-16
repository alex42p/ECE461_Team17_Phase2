# 📸 MVP Search Endpoint - Screenshot Guide

## Endpoint: `GET /packages/byRegex`

---

## 🎯 Why This Endpoint for MVP?

### **Better Than Simple `/id` Lookup:**

1. **Discovery vs. Retrieval**
   - `/package/<id>` requires exact ID knowledge (not realistic)
   - `/byRegex` enables **real-world package discovery**
   - Users can find packages by name patterns

2. **Shows Advanced Features**
   - ✅ **Regex pattern matching** - shows query parsing
   - ✅ **Multi-package handling** - not just single lookups
   - ✅ **Score-based sorting** - demonstrates data aggregation
   - ✅ **Filtering logic** - shows backend intelligence

3. **Production-Ready Design**
   - Query parameters (`?RegEx=...`)
   - Error handling for invalid regex
   - Sorted results by quality
   - Proper HTTP status codes

### **Better Than Simple `/artifacts` List:**

- Not just dumping all data
- **Intelligent filtering** with regex
- Shows the system can handle **complex queries**
- Demonstrates **scoring integration** (sorted by net_score)

---

## ✅ What It Implements

1. **Regex Pattern Matching**
   - Case-insensitive search
   - Full regex syntax support (`bert.*uncased`, `^gpt`, etc.)
   - Validates regex before searching

2. **Quality-Based Sorting**
   - Results sorted by `net_score` (highest first)
   - Promotes high-quality packages
   - Shows scoring system integration

3. **Multiple Package Handling**
   - Scans all packages in storage
   - Returns array of matching results
   - Includes count for quick reference

4. **Comprehensive Response**
   - Package ID, name, version
   - Full scoring details
   - URL and metadata
   - Applied regex pattern

---

## 🚧 What's Missing (MVP Scope)

1. **Pagination** - Returns all results (acceptable for small datasets)
2. **Advanced Filters** - No date, author, or tag filters yet
3. **Full-Text Search** - Only searches names, not descriptions
4. **Performance Optimization** - Linear scan (fine for MVP)
5. **Caching** - No result caching (future enhancement)

---

## 🚀 How to Test & Capture Screenshot

### **Setup (Terminal 1)**

```bash
# Navigate to project
cd /Users/george/ECE461_Team17/ECE461_Team17_Phase2

# Activate virtual environment
source venv/bin/activate

# Set GitHub token
export GITHUB_TOKEN="your_github_token_here"

# Start server
cd src
python3 app.py
```

You should see:
```
============================================================
  ECE461 Team 17 - Package Registry API
============================================================

Endpoints:
  POST /package              - Ingest and score a package
  GET  /package/<id>         - Retrieve package by ID
  GET  /packages/byRegex     - Search packages by regex

Listening on http://127.0.0.1:8080
============================================================
```

---

### **Upload Test Packages (Terminal 2)**

```bash
# Package 1: BERT base
curl -X POST http://127.0.0.1:8080/package \
  -H "Content-Type: application/json" \
  -d '{
    "name": "bert-base-uncased",
    "version": "1.0.0",
    "url": "https://huggingface.co/bert-base-uncased"
  }'

# Package 2: BERT large
curl -X POST http://127.0.0.1:8080/package \
  -H "Content-Type: application/json" \
  -d '{
    "name": "bert-large-uncased",
    "version": "1.0.0",
    "url": "https://huggingface.co/bert-large-uncased"
  }'

# Package 3: GPT-2
curl -X POST http://127.0.0.1:8080/package \
  -H "Content-Type: application/json" \
  -d '{
    "name": "gpt2",
    "version": "1.0.0",
    "url": "https://huggingface.co/gpt2"
  }'
```

---

## 📸 Screenshot Commands

### **🏆 BEST FOR MVP (Recommended):**

```bash
curl "http://127.0.0.1:8080/packages/byRegex?RegEx=bert"
```

**Why This One?**
- Shows regex matching (finds 2 BERT models)
- Demonstrates sorting (by net_score)
- Shows multiple results
- Clean, readable output

**Expected Response:**
```json
{
  "success": true,
  "count": 2,
  "regex_pattern": "bert",
  "packages": [
    {
      "id": "bert-base-uncased-1.0.0-abc123",
      "name": "bert-base-uncased",
      "version": "1.0.0",
      "url": "https://huggingface.co/bert-base-uncased",
      "scores": {
        "net_score": {"value": 0.82},
        "ramp_up_time": {"value": 0.85, "latency_ms": 123},
        "license": {"value": 1.0, "latency_ms": 45},
        ...
      },
      "created_at": "2025-11-03T..."
    },
    {
      "id": "bert-large-uncased-1.0.0-def456",
      "name": "bert-large-uncased",
      ...
    }
  ]
}
```

---

### **Alternative Screenshots:**

#### 1. **Advanced Regex Pattern:**
```bash
curl "http://127.0.0.1:8080/packages/byRegex?RegEx=bert.*uncased"
```
*Shows complex regex capability*

#### 2. **Prefix Search:**
```bash
curl "http://127.0.0.1:8080/packages/byRegex?RegEx=^gpt"
```
*Shows anchor patterns (^ = start of string)*

#### 3. **Case-Insensitive Search:**
```bash
curl "http://127.0.0.1:8080/packages/byRegex?RegEx=BERT"
```
*Shows case-insensitive matching*

---

## 🎨 Pretty JSON Output (Optional)

Install `jq` for formatted output:
```bash
brew install jq  # macOS
```

Then use:
```bash
curl -s "http://127.0.0.1:8080/packages/byRegex?RegEx=bert" | jq
```

---

## 📋 MVP Submission Notes

### **Include in Your Screenshot Caption:**

**Endpoint Implemented:** `GET /packages/byRegex?RegEx=<pattern>`

**What Works:**
- ✅ Regex pattern matching (case-insensitive)
- ✅ Results sorted by net score (descending)
- ✅ Multiple package results
- ✅ Full scoring details included
- ✅ Error handling for invalid regex
- ✅ Query parameter parsing

**Why This Endpoint:**
- Demonstrates **package discovery** (more realistic than ID lookup)
- Shows **advanced filtering** with regex patterns
- Integrates **scoring system** (sorted by quality)
- Handles **multiple packages** (not just single retrieval)
- Production-ready **query parameter** interface

**What's Missing:**
- Pagination for large result sets
- Additional filters (date, author, tags)
- Full-text search beyond names
- Result caching for performance

**Implementation:**
- File-based JSON storage
- Python regex matching (`re` module)
- Automatic score-based sorting
- Comprehensive error handling

---

## ✅ Success Criteria for Screenshot

Your screenshot should clearly show:

1. ✅ **The curl command** with `RegEx` parameter
2. ✅ **JSON response** with:
   - `"success": true`
   - `"count": X`
   - `"regex_pattern": "..."`
   - `"packages": [array of results]`
3. ✅ **Package details** including:
   - ID, name, version, URL
   - Full `scores` object with `net_score`
   - `created_at` timestamp
4. ✅ **Multiple packages** (if pattern matches more than one)
5. ✅ **Sorted results** (highest score first)

---

## 🚨 Common Issues

### **Error: "RegEx parameter is required"**
```bash
# ❌ Wrong:
curl http://127.0.0.1:8080/packages/byRegex

# ✅ Correct:
curl "http://127.0.0.1:8080/packages/byRegex?RegEx=bert"
```

### **Error: "Invalid regex pattern"**
```bash
# ❌ Wrong:
curl "http://127.0.0.1:8080/packages/byRegex?RegEx=[unclosed"

# ✅ Correct:
curl "http://127.0.0.1:8080/packages/byRegex?RegEx=bert"
```

### **No Results**
- Make sure you uploaded packages first
- Check that package names match your regex
- Try a simpler pattern like `.*` to see all packages

---

## 🎯 Quick Test Script

Save as `test_search.sh`:

```bash
#!/bin/bash

BASE_URL="http://127.0.0.1:8080"

# Search for packages matching 'bert'
curl -s "$BASE_URL/packages/byRegex?RegEx=bert" | jq
```

Run: `chmod +x test_search.sh && ./test_search.sh`

---

## 🌐 Testing on Cloud (AWS)

If deployed to AWS:

```bash
# Replace with your AWS EC2 public IP/domain
curl "http://your-ec2-instance.amazonaws.com/packages/byRegex?RegEx=bert"
```

**Screenshot Note:** Mention "Tested locally" or "Cloud deployed" in your caption.

