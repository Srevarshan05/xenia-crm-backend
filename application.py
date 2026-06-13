import uvicorn
from app.main import app as application

if __name__ == "__main__":
    uvicorn.run("application:application", host="0.0.0.0", port=8000)
