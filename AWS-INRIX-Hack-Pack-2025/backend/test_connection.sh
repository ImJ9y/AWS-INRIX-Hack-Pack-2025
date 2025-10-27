#!/bin/bash

echo "=========================================="
echo "TESTING FALL DETECTION SYSTEM"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Check .env file
echo "Test 1: Checking .env file..."
if [ -f ".env" ]; then
    echo -e "${GREEN}OK .env file exists${NC}"
    if grep -q "GOOGLE_API_KEY" .env; then
        API_KEY=$(grep "GOOGLE_API_KEY" .env | cut -d'=' -f2)
        if [ ! -z "$API_KEY" ] && [ "$API_KEY" != "your_api_key_here" ]; then
            echo -e "${GREEN}OK GOOGLE_API_KEY is configured${NC}"
            echo "   Key: ${API_KEY:0:20}..."
        else
            echo -e "${RED}ERROR GOOGLE_API_KEY is not set properly${NC}"
            echo -e "${YELLOW}   Please add your API key to .env${NC}"
        fi
    else
        echo -e "${RED}ERROR GOOGLE_API_KEY not found in .env${NC}"
    fi
else
    echo -e "${RED}ERROR .env file not found!${NC}"
    echo -e "${YELLOW}Creating .env template...${NC}"
    echo "GOOGLE_API_KEY=your_api_key_here" > .env
    echo -e "${YELLOW}NOTE Please edit backend/.env and add your API key${NC}"
    echo -e "${YELLOW}   Get one at: https://aistudio.google.com/app/apikey${NC}"
fi
echo ""

# Test 2: Check Python files
echo "Test 2: Checking Python files..."
if [ -f "analyze_fall/analyze.py" ]; then
    echo -e "${GREEN}OK analyze.py exists${NC}"
else
    echo -e "${RED}ERROR analyze.py not found${NC}"
fi

if [ -f "simple_backend.py" ]; then
    echo -e "${GREEN}OK simple_backend.py exists${NC}"
else
    echo -e "${RED}ERROR simple_backend.py not found${NC}"
fi
echo ""

# Test 3: Check Python dependencies
echo "Test 3: Checking Python dependencies..."
python3 -c "import flask" 2>/dev/null && echo -e "${GREEN}OK flask installed${NC}" || echo -e "${RED}ERROR flask not installed${NC}"
python3 -c "import requests" 2>/dev/null && echo -e "${GREEN}OK requests installed${NC}" || echo -e "${RED}ERROR requests not installed${NC}"
python3 -c "from dotenv import load_dotenv" 2>/dev/null && echo -e "${GREEN}OK python-dotenv installed${NC}" || echo -e "${RED}ERROR python-dotenv not installed${NC}"
echo ""

# Test 4: Try importing Gemini analyzer
echo "Test 4: Testing Gemini analyzer import..."
python3 -c "import sys; sys.path.append('.'); from analyze_fall.analyze import EmergencyImageAnalyzer; print('OK Gemini analyzer can be imported')" 2>&1 | grep -q "OK" && echo -e "${GREEN}OK Gemini analyzer imports successfully${NC}" || echo -e "${YELLOW}WARNING  Import issue detected${NC}"
echo ""

echo "=========================================="
echo "SUMMARY SUMMARY"
echo "=========================================="
echo ""
echo "To start the system:"
echo ""
echo "Terminal 1 - Backend:"
echo "  cd backend"
echo "  python3 simple_backend.py"
echo ""
echo "Terminal 2 - Frontend:"
echo "  cd frontend"
echo "  pnpm dev"
echo ""
echo "Then open: http://localhost:5173"
echo ""
echo "=========================================="

