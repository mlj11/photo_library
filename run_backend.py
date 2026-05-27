import os, sys

sys.path.insert(0, r'c:\photo-library\backend')
os.chdir(r'c:\photo-library\backend')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
