import concurrent.futures
import json
import math
import os
import re
from datetime import datetime
from uuid import uuid4
from xml.dom import ValidationErr
from zipfile import ZipFile

import requests
from django.conf import settings
from gpxpy.gpx import GPX, GPXTrack, GPXTrackSegment, GPXWaypoint
from tqdm import tqdm

from .models import AOI, FeedbackAOI, FeedbackLabel, Label
from .serializers import FeedbackLabelSerializer, LabelSerializer


def get_dir_size(directory):
    total_size = 0
    for entry in os.scandir(directory):
        if entry.is_file():
            total_size += entry.stat().st_size
        elif entry.is_dir():
            total_size += get_dir_size(entry.path)
    return total_size


def bbox(coord_list):
    """_summary_

    Args:
        coord_list (_type_): Polygon coordinate list

    Returns:
        list: bbox coords

    """
    box = []
    for i in (0, 1):
        res = sorted(coord_list, key=lambda x: x[i])
        box.append((res[0][i], res[-1][i]))
    correction = 0.000001  # need crctn because coordinate comming from js
    ret = [
        box[0][0] + correction,
        box[1][0] + correction,
        box[0][1] - correction,
        box[1][1] - correction,
    ]
    return ret


def convert2worldcd(lat, lng, tile_size):
    """
    World coordinates  are measured from the Mercator projection's origin
    (the northwest corner of the map at 180 degrees longitude and
    approximately 85 degrees latitude) and increase in the x direction
    towards the east (right) and increase in the y direction towards the south
    (down).Because the basic Mercator  tile is 256 x 256 pixels, the usable
    world coordinate space is {0-256}, {0-256}
    """
    siny = math.sin((lat * math.pi) / 180)
    siny = min(max(siny, -0.9999), 0.9999)
    world_x = tile_size * (0.5 + (lng / 360))
    world_y = tile_size * (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi))
    # print("world coordinate space is %s, %s",world_x,world_y)
    return world_x, world_y


def latlng2tile(zoom, lat, lng, tile_size):
    """By dividing the pixel coordinates by the tile size and taking the
    integer parts of the result, you produce as a by-product the tile
    coordinate at the current zoom level."""
    zoom_byte = 1 << zoom  # converting zoom level to pixel bytes
    # print(zoom_byte)
    w_x, w_y = convert2worldcd(lat, lng, tile_size)

    t_x = math.floor((w_x * zoom_byte) / tile_size)
    t_y = math.floor((w_y * zoom_byte) / tile_size)
    return t_x, t_y


def get_start_end_download_coords(bbox_coords, zm_level, tile_size):
    # start point where we will start downloading the tiles

    start_point_lng = bbox_coords[0]  # getting the starting lat lng
    start_point_lat = bbox_coords[1]

    # end point where we should stop downloading the tile
    end_point_lng = bbox_coords[2]  # getting the ending lat lng
    end_point_lat = bbox_coords[3]

    # Note :  lat=y-axis, lng=x-axis
    # getting tile coordinate for first point of bbox
    start_x, start_y = latlng2tile(
        zoom=zm_level,
        lat=start_point_lat,
        lng=start_point_lng,
        tile_size=tile_size,
    )
    start = [start_x, start_y]

    # getting tile coordinate for last point of bbox
    end_x, end_y = latlng2tile(
        zoom=zm_level,
        lat=end_point_lat,
        lng=end_point_lng,
        tile_size=tile_size,
    )
    end = [end_x, end_y]
    return start, end


import logging


def download_image(url, base_path, source_name):
    response = requests.get(url)
    image = response.content
    pattern = r"/(\d+)/(\d+)/(\d+)(?:\.\w+)?"
    match = re.search(pattern, url)
    # filename = z-x-y
    filename = f"{base_path}/{source_name}-{match.group(2)}-{match.group(3)}-{match.group(1)}.png"

    with open(filename, "wb") as f:
        f.write(image)


def download_imagery(start: list, end: list, zm_level, base_path, source="maxar"):
    """Downloads imagery from start to end tile coordinate system

    Args:
        start (list):[tile_x,tile_y]
        end (list): [tile_x,tile_y],
        source (string): it should be eithre url string or maxar value
        zm_level : Zoom level
    """

    begin_x = start[0]  # this will be the beginning of the download loop for x
    begin_y = start[1]  # this will be the beginning of the download loop for x
    stop_x = end[0]  # this will be the end of the download loop for x
    stop_y = end[1]  # this will be the end of the download loop for x

    print(f"Download starting from {start} to {end} using source {source} - {zm_level}")

    start_x = begin_x  # starting loop from beginning
    start_y = begin_y  # starting y loop from beginnig
    source_name = "OAM"  # default
    download_urls = []
    while start_x <= stop_x:  # download  x section while keeping y as c
        start_y = begin_y
        while start_y >= stop_y:  # download  y section while keeping x as c
            download_path = [start_x, start_y]
            if source == "maxar":
                try:
                    connect_id = os.environ.get("MAXAR_CONNECT_ID")
                except Exception as ex:
                    raise ex
                source_name = source
                download_url = f"https://services.digitalglobe.com/earthservice/tmsaccess/tms/1.0.0/DigitalGlobe:ImageryTileService@EPSG:3857@jpg/{zm_level}/{download_path[0]}/{download_path[1]}.jpg?connectId={connect_id}&flipy=true"

            else:
                # source should be url as string , like this :  https://tiles.openaerialmap.org/62dbd947d8499800053796ec/0/62dbd947d8499800053796ed/{z}/{x}/{y}
                if "{-y}" in source:
                    ## negative TMS
                    source_value = source.replace("{-y}", "{y}")
                    # conversion from normal tms
                    y_value = int((2**zm_level) - download_path[1] - 1)

                else:
                    # If it doesn't, use the positive y-coordinate
                    y_value = download_path[1]
                    source_value = source
                download_url = source_value.format(
                    x=download_path[0], y=y_value, z=zm_level)
            download_urls.append(download_url)

            start_y = start_y - 1  # decrease the y

        start_x = start_x + 1  # increase the x

    # Use the ThreadPoolExecutor to download the images in parallel

    # with concurrent.futures.ThreadPoolExecutor() as executor:
    #     for url in download_urls:
    #         executor.submit(download_image, url, base_path, source_name)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(download_image, url, base_path, source_name)
            for url in download_urls
        ]

        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error occurred: {e}")
                raise e


def download(
    bbox,
    zoom_level,
    tms_url,
    tile_size=256,
    download_path=None,
):
    start, end = get_start_end_download_coords(bbox, zoom_level, tile_size)
    download_imagery(
        start,
        end,
        zoom_level,
        base_path=download_path,
        source=tms_url,
    )
    return download_path


def is_dir_empty(directory_path):
    return not any(os.scandir(directory_path))


def request_rawdata(request_params):
    """will make call to galaxy API & provides response as json

    Args:
        request_params (dict): Galaxy API Request Body

    Raises:
        ImportError: If galaxy url is not exists

    Returns:
        Response(json): API Response
    """

    export_tool_api_url = settings.EXPORT_TOOL_API_URL

    # following block should be a background task
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }
    print(request_params)
    with requests.post(
        url=export_tool_api_url, data=json.dumps(request_params), headers=headers
    ) as r:  # curl can also be option
        r.raise_for_status()
        response_back = r.json()
        print(response_back)
        return response_back


def process_rawdata(file_download_url, aoi_id, feedback=False):
    """This will create temp directory , Downloads file from URL provided,
    Unzips it Finds a geojson file , Process it and finally removes
    processed Geojson file and downloaded zip file from Directory"""
    r = requests.get(file_download_url)
    # Check whether the export path exists or not
    path = "temp/"
    isExist = os.path.exists(path)
    if not isExist:
        # Create a exports directory because it does not exist
        os.makedirs(path)
    file_temp_path = os.path.join(path, f"{str(uuid4())}.zip")  # unique
    open(file_temp_path, "wb").write(r.content)
    print("Zip File from API wrote to disk")
    with ZipFile(file_temp_path, "r") as zipObj:
        # Get a list of all archived file names from the zip
        listOfFileNames = zipObj.namelist()
        # Iterate over the file names
        geojson_file_path = f"""{path}/geojson/"""

        for fileName in listOfFileNames:
            # Check filename endswith csv
            if fileName.endswith(".geojson"):
                if fileName != "clipping_boundary.geojson":
                    # Extract a single file from zip
                    zipObj.extract(fileName, geojson_file_path)
                    print(f"""Geojson file{fileName} from API wrote to disk""")
                    break
        geojson_file = f"""{geojson_file_path}{fileName}"""
        process_geojson(geojson_file, aoi_id, feedback)
    remove_file(file_temp_path)
    remove_file(geojson_file)


def remove_file(path: str) -> None:
    """Used for removing temp file"""
    os.unlink(path)


def gpx_generator(geom_json):
    """Generates GPX for give geojson geometry

    Args:
        geom_json (_type_): _description_

    Returns:
        xml: gpx
    """

    gpx = GPX()
    gpx_track = GPXTrack()
    gpx.tracks.append(gpx_track)
    gpx_segment = GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)
    for point in geom_json["coordinates"][0]:
        # Append each point as a GPXWaypoint to the GPXTrackSegment
        gpx_segment.points.append(GPXWaypoint(point[1], point[0]))
    gpx.creator = "fAIr"
    gpx_track.name = "Don't Edit this Boundary"
    gpx_track.description = "Map inside this boundary and go back to fAIr UI"
    gpx.time = datetime.now()
    gpx.link = "https://github.com/hotosm/fAIr"
    gpx.link_text = "AI Assisted Mapping - fAIr : HOTOSM"
    return gpx.to_xml()


def process_feature(feature, aoi_id, foreign_key_id, feedback=False):
    """Multi thread process of features"""
    properties = feature["properties"]
    osm_id = properties["osm_id"]
    geometry = feature["geometry"]
    if feedback:
        if FeedbackLabel.objects.filter(
            osm_id=int(osm_id), feedback_aoi__training=foreign_key_id
        ).exists():
            FeedbackLabel.objects.filter(
                osm_id=int(osm_id), feedback_aoi__training=foreign_key_id
            ).delete()

        label = FeedbackLabelSerializer(
            data={"osm_id": int(osm_id), "geom": geometry, "feedback_aoi": aoi_id}
        )

    else:
        if Label.objects.filter(
            osm_id=int(osm_id), aoi__dataset=foreign_key_id
        ).exists():
            Label.objects.filter(
                osm_id=int(osm_id), aoi__dataset=foreign_key_id
            ).delete()

        label = LabelSerializer(
            data={"osm_id": int(osm_id), "geom": geometry, "aoi": aoi_id}
        )
    if label.is_valid():
        label.save()
    else:
        raise ValidationErr(label.errors)


def process_geojson(geojson_file_path, aoi_id, feedback=False):
    """Responsible for Processing Geojson file from directory ,
        Opens the file reads the record , Checks either record
        present or not if not inserts into database

    Args:
        geojson_file_path (_type_): _description_
        aoi_id (_type_): _description_

    Raises:
        ValidationErr: _description_
    """
    print("Geojson Processing Started")
    if feedback:
        foreign_key_id = FeedbackAOI.objects.get(id=aoi_id).training
    else:
        foreign_key_id = AOI.objects.get(id=aoi_id).dataset
    max_workers = (
        (os.cpu_count() - 1) if os.cpu_count() != 1 else 1
    )  # leave one cpu free always

    # max_workers = os.cpu_count()  # get total cpu count available on the

    with open(geojson_file_path) as f:
        data = json.load(f)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    process_feature, feature, aoi_id, foreign_key_id, feedback
                )
                for feature in data["features"]
            ]
            for f in tqdm(futures, total=len(data["features"])):
                f.result()

    print("writing to database finished")
