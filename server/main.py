from typing import List

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse


import hashlib
import redis
import fastapi_plugins
from pymongo import MongoClient
from pydantic import BaseModel

client = MongoClient('database', 27017)
database = client['result_database']
image_results = database['image_results']
app = FastAPI()


class ImageResult(BaseModel):
    fileName: str
    hash: str
    result: str

# Must have CORSMiddleware to enable localhost client and server
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5057",
    "http://localhost:5000",
    "http://localhost:6379",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    # connect to redis
    client = redis.Redis(host='redis', port=6379)

    # set a key
    client.set('test-key', 'test-value')

    # get a value
    value = client.get('test-key')
    return {"message": value}


@app.post("/predict")
async def get_prediction(images: List[UploadFile] = File(...)):
    BUF_SIZE = 65536 # Read image data in 64KB Chunks for hashlib
    hashes = {}

    for upload_file in images:
        f = upload_file.file
        md5 = hashlib.md5()
        while True:
            data = f.read(BUF_SIZE)
            if not data:
                break
            md5.update(data)
        hashes[upload_file.filename] = md5.hexdigest()

    return {"images": [hashes[key] for key in hashes]}


@app.get('/images')
async def list_images():
    images = []
    for image in image_results.find():
        images.append(ImageResult(**image))
    return {'images': images}

@app.post('/images')
async def process_image(image: ImageResult):
    ret = image_results.insert_one(image.dict(by_alias=True))
    return {'images': ret}