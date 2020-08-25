import numpy as np
import pandas as pd
import datetime as dt

import sqlalchemy
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, func

from flask import Flask, jsonify

# Create engine 
engine = create_engine("sqlite:///Resources/hawaii.sqlite")
# reflect an existing database into a new model
# automap documentation - https://docs.sqlalchemy.org/en/13/orm/extensions/automap.html
Base = automap_base()
# reflect the tables
Base.prepare(engine, reflect=True)
# Save references to each table
Measurement = Base.classes.measurement
Station = Base.classes.station

#################################################
# Flask Setup
#################################################
app = Flask(__name__)

#################################################
# Flask Routes
#################################################
@app.route("/")
def welcome():
    """List all available api routes"""
    return (
        f"Available Routes:<br/>"
        f"/api/v1.0/precipitation --- precipitation and their dates<br/>"
        f"/api/v1.0/stations --- Station information<br/>"
        f"/api/v1.0/tobs --- Last 12 months temperature observation from the most active station<br/>"
        f"/api/v1.0/(start) --- Each day is the average of each identical day for all years<br/>"+
                f"---(start): enter month you want to start query returns all days after start. Enter (mmdd)<br/>"
        f"/api/v1.0/(start)/(end) --- Each day is the average of each identical day for all years<br/>"+
                f"---(start): enter month you want to start query. Enter (mmdd)<br/>"+
                f"---(end): enter month you want to end query. Enter (mmdd)<br/>"
    )

@app.route("/api/v1.0/precipitation")
def precipitation():
    # Create our session (link) from Python to the DB
    session = Session(engine)
    # Calculate the date 1 year ago from the last data point in the database
    ## Get most recent day and convert to datetime object
    most_recent_day = session.query(Measurement.date).order_by(Measurement.date.desc()).first()
    dt_obj = dt.datetime.strptime(most_recent_day[0], '%Y-%m-%d')
    ## Subract a year to find datetime object of date from a year earlier of most_recent_day
    year_ago = dt.date(dt_obj.year-1,dt_obj.month,dt_obj.day)

    # Perform a query to retrieve the date and precipitation scores
    last_year_prcp = session.query(Measurement.date,Measurement.prcp).\
                            filter(Measurement.date >= year_ago).all()
    
    session.close()
    # make a list as the date (key) is not necessarily unique
    prcp_l = []
    for date, prcp in last_year_prcp: # store precipitation values in date keys and jsonify the list
        if date != None and prcp != None:
            prcp_d = {}
            prcp_d[date] = prcp
            prcp_l.append(prcp_d)
    return jsonify(prcp_l)

@app.route("/api/v1.0/stations")
def stations():
    # Create our session (link) from Python to the DB
    session = Session(engine)

    # Query all stations
    station_info = session.query(Station.station,Station.name,Station.latitude,Station.longitude,Station.elevation).all()

    session.close()

    stations_d = {}
    for stat,name,lat,lon,ele in station_info:
        stations_d[stat] = {'Name':name, 'Latitude':lat,'Longitude':lon,'Elevation':ele}

    return jsonify(stations_d)

@app.route("/api/v1.0/tobs")
def tobs():
    # Create our session (link) from Python to the DB
    session = Session(engine)

    # query all measurement to find the most active station (which one appears the most)
    station_freq = session.query(Measurement.station,func.count(Measurement.station)).\
                group_by(Measurement.station).order_by(func.count(Measurement.station).desc()).all()
    most_active_station = str(station_freq[0][0])

    # Calculate the date 1 year ago from the last data point in the database
    ## Get most recent day and convert to datetime object
    most_recent_day = session.query(Measurement.date).order_by(Measurement.date.desc()).first()
    dt_obj = dt.datetime.strptime(most_recent_day[0], '%Y-%m-%d')
    ## Subract a year to find datetime object of date from a year earlier of most_recent_day
    year_ago = dt.date(dt_obj.year-1,dt_obj.month,dt_obj.day)

    # Choose the station with the highest number of temperature observations.
    # Query the last 12 months of temperature observation data for this station and plot the results as a histogram
    last_year_temp = session.query(Measurement.tobs,Measurement.date).\
                            filter(Measurement.station == most_active_station).\
                            filter(Measurement.date >= year_ago).all() # year_ago from the begining of notebook

    session.close()

    return jsonify(last_year_temp)


@app.route("/api/v1.0/<start>")
def after_date(start):
    # Create our session (link) from Python to the DB
    session = Session(engine)
    ## Functions for use in next routes
    # Function for finding TMIN,TAVG,TMAX
    def daily_normals(date):
        """Daily Normals.
        
        Args:
            date (str): A date string in the format '%m-%d'
            
        Returns:
            A list of tuples containing the daily normals, tmin, tavg, and tmax
        
        """
        sel = [func.min(Measurement.tobs), func.avg(Measurement.tobs), func.max(Measurement.tobs)]
        return session.query(*sel).filter(func.strftime("%m-%d", Measurement.date) == date).all()
    # Function to get desired date format
    def str_that_date(m,d):
        """
        Args:
            m (int): input month as an integer
            d (int): input day as an integer
        Returns:
            A string of the date in apporopriate formating"""
        
        if m < 10:
            month = '0'+str(m)
        else:
            month = str(m)
        
        if d < 10:
            day = '0'+str(d)
        else:
            day = str(d)
        return (month+'-'+day)
    # Function for selection data from date ragne provided
    def weather_for_trip(start_month,start_day,end_month,end_day,big_df):
        """
        Args:
            start_month (int): input start month of trip as an integer
            start_day (int): input start day of trip as an integer
            end_month (int): input end month of trip as an integer
            end_day (int): input end day of trip as an integer
            big_df (pd.DataFrame): input dataframe with average values for each day
        Returns:
            A dataframe with temperature infor over duration of trip
        """
        temp_df = big_df.loc[(big_df['INT Date'] >= 
                                int(str_that_date(start_month,start_day).replace('-',''))),:]
        temp_df = temp_df.loc[(temp_df['INT Date'] <= 
                            int(str_that_date(end_month,end_day).replace('-',''))), :]
        temp_df = temp_df.drop(columns='INT Date')
        return temp_df
    # loop through each day of each month and store in list
    days_info = []
    date_true = []
    for m in range(1,12+1): # loop through all possible months (1-12)
        for d in range(1,31+1): # loop through all possible days (1-31)
            # calculate the daily normals for each day and append to list
            temp = daily_normals(str_that_date(m,d))
            if temp[0][0] != None: # filter out the days that didn't exists/have data for
                days_info.append(list(*temp))
                date_true.append(str_that_date(m,d))
    session.close()           

    # Store query into a dataframe, add the dates, and rename the columns
    normal_df = pd.DataFrame(days_info)
    normal_df['date'] = date_true
    normal_df = normal_df.set_index('date')
    normal_df = normal_df.rename(columns={0:"Min Temp",1:"Avg Temp",2:"Max Temp"})
    # add a int style date for easy filtering
    date_int = [int(x.replace('-','')) for x in date_true]
    normal_df['INT Date'] = date_int
    
    st = dt.datetime.strptime(start,"%m-%d")
    result_df = weather_for_trip(st.month,st.day,12,31,normal_df).to_dict('index')

    return jsonify(result_df)

# Next route is almost identical, but with just another variable
@app.route("/api/v1.0/<start>/<end>")
def between_date(start,end):
    # Create our session (link) from Python to the DB
    session = Session(engine)
    ## Functions for use in next routes
    # Function for finding TMIN,TAVG,TMAX
    def daily_normals(date):
        """Daily Normals.
        
        Args:
            date (str): A date string in the format '%m-%d'
            
        Returns:
            A list of tuples containing the daily normals, tmin, tavg, and tmax
        
        """
        sel = [func.min(Measurement.tobs), func.avg(Measurement.tobs), func.max(Measurement.tobs)]
        return session.query(*sel).filter(func.strftime("%m-%d", Measurement.date) == date).all()
    # Function to get desired date format
    def str_that_date(m,d):
        """
        Args:
            m (int): input month as an integer
            d (int): input day as an integer
        Returns:
            A string of the date in apporopriate formating"""
        
        if m < 10:
            month = '0'+str(m)
        else:
            month = str(m)
        
        if d < 10:
            day = '0'+str(d)
        else:
            day = str(d)
        return (month+'-'+day)
    # Function for selection data from date ragne provided
    def weather_for_trip(start_month,start_day,end_month,end_day,big_df):
        """
        Args:
            start_month (int): input start month of trip as an integer
            start_day (int): input start day of trip as an integer
            end_month (int): input end month of trip as an integer
            end_day (int): input end day of trip as an integer
            big_df (pd.DataFrame): input dataframe with average values for each day
        Returns:
            A dataframe with temperature infor over duration of trip
        """
        temp_df = big_df.loc[(big_df['INT Date'] >= 
                                int(str_that_date(start_month,start_day).replace('-',''))),:]
        temp_df = temp_df.loc[(temp_df['INT Date'] <= 
                            int(str_that_date(end_month,end_day).replace('-',''))), :]
        temp_df = temp_df.drop(columns='INT Date')
        return temp_df
    # loop through each day of each month and store in list
    days_info = []
    date_true = []
    for m in range(1,12+1): # loop through all possible months (1-12)
        for d in range(1,31+1): # loop through all possible days (1-31)
            # calculate the daily normals for each day and append to list
            temp = daily_normals(str_that_date(m,d))
            if temp[0][0] != None: # filter out the days that didn't exists/have data for
                days_info.append(list(*temp))
                date_true.append(str_that_date(m,d))
    session.close()           

    # Store query into a dataframe, add the dates, and rename the columns
    normal_df = pd.DataFrame(days_info)
    normal_df['date'] = date_true
    normal_df = normal_df.set_index('date')
    normal_df = normal_df.rename(columns={0:"Min Temp",1:"Avg Temp",2:"Max Temp"})
    # add a int style date for easy filtering
    date_int = [int(x.replace('-','')) for x in date_true]
    normal_df['INT Date'] = date_int
    
    st = dt.datetime.strptime(start,"%m-%d")
    ed = dt.datetime.strptime(end,"%m-%d")
    result_df = weather_for_trip(st.month,st.day,ed.month,ed.day,normal_df).to_dict('index')

    return jsonify(result_df)

if __name__ == '__main__':
    app.run(debug=True)
