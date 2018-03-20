#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Fri Mar  9 08:02:42 2018

@author: taisgrippa
"""

## Import libs
import pandas as pd
import geopandas as gpd
import urllib
import tempfile
import sys
import os
import time
from ast import literal_eval

######
######### USER DEFINED PARAMETERS ############
######
## Path to input shapefile with points
input_shape="/YOUR PARTH TO YOUR DATA/Shape_locations.shp"
## Output folder path
outputfolder="YOUR PARTH TO YOUR OUTPUT FOLDER"
## Define the personnal key for openrouteservice.org API
## API Key can be asked here https://openrouteservice.org/dev-dashboard/
my_personal_key="YOUR PERSONNAL API KEY"

#### API parameters for "isochrones-services" - https://openrouteservice.org/documentation/#/reference/isochrones/isochrones/isochrones-service
## Set the desired parameters for the request
request_param={}
request_param['locations']="{locations_coordinates}"
request_param['profile']="foot-walking"  # Choose between driving-car , driving-hgv , cycling-regular , cycling-road , cycling-safe , cycling-mountain , cycling-tour , foot-walking , foot-hiking
request_param['range_type']="time"
request_param['range']=1200  # Should not be more than 10 time the 'interval'
request_param['interval']=120
request_param['units']=""   # If 'range_type'='distance'
request_param['location_type']="start"
request_param['attributes']="area|total_pop"
request_param['options']=""
request_param['intersections']=""
request_param['id']=""

#### Check for potential problems in the input shapefile
# The geometry should be point
points_gdf=gpd.read_file(input_shape)
if str(points_gdf['geometry'][0])[:5] != "POINT":
    sys.exit("ERROR: The shapefile provided should contains 'POINT' geometries.")
# The CRS should be WGS84 (EPSG:4326)
if points_gdf.crs['init']!='epsg:4326':
    os.error("Input Shapefile's EPSG is not 4326.")

#### Check for potential problems in the parameters
#TODO: Add all exceptions according to https://openrouteservice.org/ratelimits/
## Define class for error raising
class ApiParameterError(Exception):
    def __init__(self, mismatch):
        Exception.__init__(self, mismatch)
# Correspondance between 'range_type' and 'units' parameter
if request_param['range_type']=="time" and request_param['units']!="": 
    try:
        raise ApiParameterError("'range_type'='time' do not support value for 'unit' parameter")
    except ApiParameterError as problem:
        print "ERROR: {0}".format(problem)
# Number of isochrone to be returned could not exceed 10
nb_iso=request_param['range']/request_param['interval']+(1 if request_param['range']%request_param['interval']>0 else 0)
if nb_iso>10: 
    try:
        raise ApiParameterError("The maximum number of isochrone to be returned is more than 10. A 'range' of %s and an 'interval' of %s will result in %s isochrones. Please adapt the parameters"%(request_param['range'],request_param['interval'],nb_iso))
    except ApiParameterError as problem:
        print "ERROR: {0}".format(problem)
                
######
######### Coordinates of locations to be used ############
######
## Set a list with XY coordinates (WGS84) of points to be used
points=[]
[points.append([row.x ,row.y]) for row in gpd.GeoSeries(points_gdf['geometry'])]
## Set a list of batch with maximum 5 locations in each batch
batch_size=5  # Define maximum number of locations per request to the API
batch_locations=[]
if len(points)==1:  # If only one location in the list
    batch_locations.append("%s,%s"%(points[0][0],points[0][1]))

if len(points)>1:   # If several locations
    if len(points)<=batch_size:    # If one API request is enough
        batch_locations.append("|".join(["%s,%s"%(coord[0],coord[1]) for coord in points]))
    else:  # If required more than one request to the API (too many locations for a single API request)
        while len(points)>batch_size:
            current_batch="|".join(["%s,%s"%(coord[0],coord[1]) for coord in points[-batch_size:]])
            batch_locations.append(current_batch)
            [points.pop() for x in points[-batch_size:]]  # Remove the points from the list
        if len(points)<=batch_size:    # If one API request is enough
            batch_locations.append("|".join(["%s,%s"%(coord[0],coord[1]) for coord in points]))

######
######### Creation of API request(s) ############
######
#### Layout of API request without location coordinates
base_url="https://api.openrouteservice.org/isochrones?api_key=%s"%my_personal_key
request_url=base_url+"&"+"&".join(["%s=%s"%(key,request_param[key]) for key in request_param.keys() if request_param[key] != ""])
## Generate a list of URL for requesting API
batch_api=[]
for coord in batch_locations:
    batch_api.append(request_url.format(locations_coordinates=coord))
    
######
######### Download GeoJson results from OpenRouteService API ############
###### 
####
temp_dir=tempfile.gettempdir()
succeed_list=[]
failed_api=[]
for i,url_api in enumerate(batch_api,1):
    temp_file=os.path.join(temp_dir,"OpenRouteServiceIsochroneApiRequest_%s.geojson"%i)
    time.sleep(3)  # Sleep could be ajusted to be more fast, but at least it works with 3 seconds. If not sleep, API rate limit error occured (40 request per minut maximum)
    urllib.urlretrieve(url_api, temp_file)
    try:
        geojson=literal_eval(open(temp_file,'r').next())
        if 'error' in geojson.keys():
            failed_api.append(url_api)
            code=geojson['error']['code']
            message=geojson['error']['message']
            print "ERROR %s in GeoJson batch %s:%s "%(code,i,message)
        else:
            succeed_list.append(temp_file)
    except:
        print "Problem to convert GeoJson file into dictionnary with literal_eval"
        failed_api.append(url_api)
        
## Check if failed_list is empty or not
if len(failed_api)>0:
    print "The following %s API request failed :\n%s"%(len(failed_api),"\n".join(failed_api))

######
######### GeoPandas merging and dissolving operations ############
###### 
list_of_df=[]    
for file_path in succeed_list:
    df = gpd.read_file(file_path)
    list_of_df.append(df)
    
concat_df=gpd.GeoDataFrame(pd.concat(list_of_df, ignore_index=True))
tmp_df=pd.DataFrame(concat_df.dissolve(by='value', aggfunc='sum'))
tmp_df.reset_index(inplace=True)
tmp_df.sort_values(by='value', ascending=False, inplace=True)
tmp_df.reset_index(drop=True, inplace=True)
tmp_df.drop(columns=['group_index'], inplace=True)
if len(file_path)>1: # If more than one API request, the resulting 'area' and 'total_pop' fields will be uncorrect
    isochrones=gpd.GeoDataFrame(tmp_df[['value','geometry']])
else:
    isochrones=gpd.GeoDataFrame(tmp_df)

#########
######### Write the final isochrone as  shapefile ############
###### 
## Create outputfolder if not exists
if not os.path.exists(outputfolder):
    os.makedirs(outputfolder)
## Write file
finalfilepath=os.path.join(outputfolder,"isochrones.shp")
isochrones.to_file(finalfilepath)

#########
######### Remove temporary files ############
###### 
[os.remove(x) for x in succeed_list]
