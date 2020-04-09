#imports 
import requests
import pprint
from datetime import datetime
import pytz
import time
import pandas as pd
import json
import os
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np

API_KEY = os.getenv('WOW_API_KEY')

def fill_missing(grp):
    res = grp.set_index('week_of_year')\
    .interpolate()\
    .fillna(method='ffill')\
    .fillna(method='bfill')
    del res['name']
    return res


def get_priest_plot(what_to_plot, data, wowlogs, player):
    if what_to_plot == 'avg-hps-raid':
        data = data[0]
        fig, axs = plt.subplots(nrows=2, figsize=(20,10))
        sns.set_palette("Paired")
        
        data_by_week = data.groupby(['week_of_year', 'name']).agg({'hps': 'mean'})
        data_by_week = data_by_week.reset_index()
        
        idx = pd.MultiIndex.from_product([data_by_week['name'].unique(), 
                                  np.arange(data_by_week['week_of_year'].min(), data_by_week['week_of_year'].max(), 1)],
                                 names=['name', 'week_of_year'])
        data_by_week = data_by_week.set_index(['name', 'week_of_year']).reindex(idx).reset_index()
        data_by_week = data_by_week.groupby(['name']).apply(
            lambda grp: fill_missing(grp)
        )
        data_by_week = data_by_week.reset_index()
        
        data_by_week['hps_rolling'] = data_by_week.groupby('name')['hps'].rolling(3).mean().reset_index(0,drop=True)
        sns.lineplot(x="week_of_year", y="hps", hue="name", 
                     data=data_by_week, ax = axs[0], hue_order = wowlogs.roster[wowlogs.wow_class])
        sns.lineplot(x="week_of_year", y="hps_rolling", hue="name", 
                     data=data_by_week, ax = axs[1], hue_order = wowlogs.roster[wowlogs.wow_class])
        axs[0].legend(loc='lower left')
        axs[1].legend(loc='lower left')
    elif what_to_plot == 'hps-by-boss':
        sns.set_palette("Paired")
        for this_data in data:
            player_data = this_data[this_data['name'] == player]
            sns.catplot(x='boss_name', y='hps', 
                hue='week_of_year', data=player_data,
                kind='bar', height=10, aspect = 1.25)
            plt.xticks(rotation=45)
        
        
def convert_date_to_utc(date):
    date = datetime.strptime(date, "%d-%m-%Y")
    return int(time.mktime(date.timetuple()))*1000

def get_bwl_reports(df_reports):
    df_reports = df_reports[df_reports['zone'] == 1002]
    return df_reports
    
def get_mc_reports(df_reports):
    df_reports = df_reports[df_reports['zone'] == 1000]
    return df_reports
    
def get_ony_reports(df_reports):
    df_reports = df_reports[df_reports['zone'] == 1001]
    return df_reports
    
def get_fights_per_raid(row):
    get_fights = 'https://classic.warcraftlogs.com:443/v1/report/fights/{code}?api_key={api_key}' \
                    .format(code = row.id,
                           api_key = API_KEY)
    fights = requests.get(get_fights)
    assert fights.status_code == 200

    df = pd.DataFrame(fights.json()['fights'])
    df = df.dropna(subset=['size'])
    df['week_of_year'] = row.week_of_year
    df['title'] = row.title
    df['zone'] = row.zone
    df['raid_start'] = row.start
    df['raid_end'] = row.end
    df['id'] = row.id
    df['boss_name'] = df['name']
    return df

def get_fights(df_raid_reports):
    fights = pd.DataFrame()
    for i, row in enumerate(df_raid_reports.iterrows()):
        temp_df = get_fights_per_raid(row[1])
        fights = fights.append(temp_df)

    fights = fights[fights.kill == True]
    fights = fights.reset_index()
    return fights

def get_data_per_fight(row, wow_class, wow_type, roster):
    if wow_type == 'Healing':
        get_data = 'https://classic.warcraftlogs.com:443/v1/report/tables/{type_of_data}/{code}?start={start}&end={end}&api_key={api_key}' \
                    .format(type_of_data = 'healing',
                            code = row.id,
                            start = row.start_time,
                            end = row.end_time,
                            api_key = API_KEY)
        data = requests.get(get_data)
        assert data.status_code == 200
        df = pd.DataFrame(data.json()['entries'])
        df = df[df['name'].isin(roster[wow_class])]
        df['fight_time'] = (row.end_time - row.start_time)/1000
        df['hps'] = df['total']/df['fight_time']
        df['week_of_year'] = row.week_of_year
        df['boss_name'] = row.boss_name
        return df
    else:
        return pd.DataFrame()

def get_data(df_raid_reports, wow_logs):
    data = pd.DataFrame()
    for i, row in enumerate(df_raid_reports.iterrows()):
        temp_df = get_data_per_fight(row[1], wow_logs.wow_class, wow_logs.wow_type, wow_logs.roster)
        data = data.append(temp_df)

    data = data.reset_index()
    del data['index']
    return data

def get_all_data(wowlogs):
    df_reports = wowlogs.get_all_reports()

    df_bwl = get_bwl_reports(df_reports)
    df_mc = get_mc_reports(df_reports)
    df_ony = get_ony_reports(df_reports)

    df_bwl_fights = get_fights(df_bwl)
    df_mc_fights = get_fights(df_mc)
    df_ony_fights = get_fights(df_ony)

    df_bwl_data = get_data(df_bwl_fights, wowlogs)
    df_mc_data = get_data(df_mc_fights, wowlogs)
    df_ony_data = get_data(df_ony_fights, wowlogs)
    
    return df_bwl_data, df_mc_data, df_ony_data

class Wowlogs:
    def __init__(self, guild_name, server, region, start_date, wow_class, wow_type, user_upload, roster):
        self.guild_name = guild_name
        self.server = server
        self.region = region
        self.start_date = start_date
        self.wow_class = wow_class
        self.wow_type = wow_type
        self.user_upload = user_upload
        self.roster = roster
        
    def get_all_reports(self):
        get_reports = 'https://classic.warcraftlogs.com:443/v1/reports/guild/{guild_name}/{server}/{region}?start= \
                        {start_date}&api_key={api_key}' \
                        .format(guild_name = self.guild_name,
                           server = self.server,
                           region = self.region,
                           start_date = convert_date_to_utc(self.start_date),
                           api_key = API_KEY)
        reports = requests.get(get_reports)
        assert reports.status_code == 200
        
        #read into df
        df = pd.read_json(reports.text)
        df['start'] = pd.to_datetime(df['start'], unit='ms')
        df['end'] = pd.to_datetime(df['end'], unit='ms')

        #add week of year
        df['week_of_year'] = df['start'].dt.week
        
        #filter for specific uploader
        df = df[df['owner'].str.match(self.user_upload)]
        return df
    
    
    
    
    

