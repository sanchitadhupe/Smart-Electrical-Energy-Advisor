# ⚡ Smart Home Energy Advisor

### AI-Powered Electricity Analysis — IBM Watsonx.ai + IBM Granite + Flask



---



## 📁 Files to Push to GitHub (ONLY these 8 items)



```

✅ app.py

✅ agent_instructions.py

✅ requirements.txt

✅ Procfile

✅ render.yaml

✅ .gitignore

✅ templates/

│   └── index.html

✅ static/

    ├── css/style.css

    └── js/app.js

```



### ❌ DO NOT push these — ever:

```

❌ .env                  ← contains your secret API key

❌ venv/                 ← 500MB of libraries, not needed

❌ __pycache__/          ← Python bytecode, not needed

```



---



## 🚀 Deploy to Render.com — Step by Step



### STEP 1 — Push code to GitHub



Open your terminal in the project folder and run these commands one by one:



```bash

git init

git add app.py agent_instructions.py requirements.txt Procfile render.yaml templates/ static/

git commit -m "Initial commit — Smart Energy Advisor"

```



Then create a new repo on https://github.com/new (name it `smart-energy-advisor`, keep it Public), and run:



```bash

git remote add origin https://github.com/YOUR_USERNAME/smart-energy-advisor.git

git branch -M main

git push -u origin main

```



> Replace `YOUR_USERNAME` with your actual GitHub username.



---



### STEP 2 — Create account on Render



1. Go to **https://render.com**

2. Click **"Get Started for Free"**

3. Sign up using your **GitHub account** (easiest — links directly)



---



### STEP 3 — Create a new Web Service on Render



1. In Render dashboard, click **"New +"** → **"Web Service"**

2. Click **"Connect a repository"**

3. Select your `smart-energy-advisor` GitHub repo

4. Click **"Connect"**



---



### STEP 4 — Configure the service



Fill in these fields:



| Field | Value |

|---|---|

| **Name** | `smart-energy-advisor` |

| **Region** | Singapore or any |

| **Branch** | `main` |

| **Runtime** | `Python 3` |

| **Build Command** | `pip install -r requirements.txt` |

| **Start Command** | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |

| **Instance Type** | `Free` |



---



### STEP 5 — Add Environment Variables (IMPORTANT)



⚠️ This is where you add your secret API key — **never put it in GitHub**.



In Render, scroll down to **"Environment Variables"** and add these 4 variables:



| Key | Value |

|---|---|

| `IBM_CLOUD_API_KEY` | `Enter Your API Key` |

| `IBM_WATSONX_PROJECT_ID` | `Enter Your Project ID` |

| `IBM_WATSONX_URL` | `Enter Your Rrgion of Project` |

| `FLASK_SECRET_KEY` | `smart_energy` |



---



### STEP 6 — Deploy



1. Click **"Create Web Service"**

2. Render will automatically:

   - Clone your GitHub repo

   - Run `pip install -r requirements.txt`

   - Start the Flask app with Gunicorn

3. Wait 2–3 minutes for the build to finish

4. Your live URL will appear at the top: **`https://smart-energy-advisor.onrender.com`**



---



### STEP 7 — Open your live app



Click the URL shown in Render dashboard — your app is now live on the internet! 🎉



> **Note:** On the free plan, Render spins down the app after 15 minutes of inactivity. The first visit after that takes ~30 seconds to wake up. This is normal for free tier.



---



## 🔄 How to Update the App Later



Whenever you make changes to your code, just run:



```bash

git add .

git commit -m "Updated something"

git push

```



Render will **automatically redeploy** within 1–2 minutes.



---



## 🧠 Tech Stack



| Layer | Technology |

|---|---|

| AI Model | IBM Granite / Llama 3.3 70B via IBM Watsonx.ai |

| Backend | Python 3.13 + Flask |

| Frontend | Bootstrap 5 + Chart.js + Vanilla JS |

| Server | Gunicorn (production WSGI) |

| Hosting | Render.com (free tier) |

| Region | IBM Sydney (au-syd.ml.cloud.ibm.com) |
