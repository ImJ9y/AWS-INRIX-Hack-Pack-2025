#  Quick Start Guide

## Step 1: Set Up Gemini API Key

1. Get your free API key: https://aistudio.google.com/app/apikey
2. Create `backend/.env` file with:

```bash
GOOGLE_API_KEY=your_actual_api_key_here
```

## Step 2: Test Everything

Run the connection test:

```bash
cd backend
chmod +x test_connection.sh
./test_connection.sh
```

This will verify:
- OK `.env` file exists
- OK API key is configured
- OK Python files are in place
- OK Dependencies are installed
- OK Gemini analyzer can be imported

## Step 3: Start Backend

```bash
cd backend
python3 simple_backend.py
```

**Look for:**
```
OK Gemini AI Analyzer loaded
 Gemini AI Analysis (ACTIVE)
```

## Step 4: Start Frontend (New Terminal)

```bash
cd frontend
pnpm install  # First time only
pnpm dev
```

## Step 5: Open Browser

Go to: **http://localhost:5173**

##  Test Features

### Test 1: Upload Video
1. Click "Upload clip"
2. Select a video
3. Let it play to end
4. See:  "Analyzing clip with AI..." →  "Professional Assessment"

### Test 2: Live Detection
1. Grant camera permission
2. Move quickly toward camera
3. Stay still for 3 seconds
4. See:  "Consulting AI doctor..." →  "Doctor's Assessment"

## WARNING Troubleshooting

### "Gemini AI (not configured)"
- Your `.env` file is missing or API key is wrong
- Create `backend/.env` with your API key
- Restart backend

### Port already in use
```bash
lsof -i :5001  # Find process
kill -9 <PID>  # Kill it
```

### Dependencies missing
```bash
cd backend
pip3 install -r requirements.txt

cd frontend
pnpm install
```

## OK Success Checklist

- [ ] `.env` file created with API key
- [ ] Backend shows "Gemini AI Analysis (ACTIVE)"
- [ ] Frontend loads at localhost:5173
- [ ] Can upload clip and see AI analysis
- [ ] Can trigger fall and see AI assessment

---

**Need help?** Run `./test_connection.sh` in the backend folder!

