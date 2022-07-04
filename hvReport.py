import sqlite3
import json
import os
import shutil
import zipfile
from flask import Flask, render_template, request, url_for, flash, redirect, jsonify
from flaskthreads import AppContextThread
from werkzeug.exceptions import abort
from werkzeug.utils import secure_filename
import altair as alt
import pandas as pd
import numpy as np
from datetime import datetime
import datetime as dt
from toolz.curried import pipe
import threading
import time

def initializeDb ():
    try:
        hvCon = sqlite3.connect('data/db/hv.db') 
        hvCur =  hvCon.cursor()
        for sData in hvData:
            for sTable in sData['data']:
                print('Creating table "{}{}" on database hv.db'.format(sData['table'], sTable['id']))
                editedColStr, editedColFloat = splitAdministratorData(sTable['parameter']['columnsStr'], sTable['parameter']['columnsFloat'])
                columnsStr = '" TEXT, "'.join(map(str, editedColStr))
                columnsStr = '"{}" TEXT'.format(columnsStr)
                if editedColFloat: 
                    columnsFloat = '" REAL, "'.join(map(str, editedColFloat))
                    columns = columnsStr + ', "' + columnsFloat + '" REAL'
                else:
                    columns = columnsStr
                sqlCommand = 'CREATE TABLE "{}{}"({})'.format(sData['table'], sTable['id'], columns)
                hvCur.execute(sqlCommand)
    except sqlite3.Error as error:
        flash("Error while connecting to sqlite", error)
    finally:
        if (hvCon):
            hvCur.close()
            hvCon.close()

def updateDb (hvStList, hvUploadDir):
    hvList = []
    try:
        hvCon = sqlite3.connect('data/db/hv.db') 
        hvCur =  hvCon.cursor()
        for hvUploadFile in hvStList:
            hvPath = hvUploadDir + '/' + hvUploadFile.replace('.', '_').replace('_zip', '')
            import zipfile
            with zipfile.ZipFile(hvUploadDir + '/' + hvUploadFile, 'r') as zipFile:
                zipFile.extractall(hvPath)
            for sData in hvData:
                for sTable in sData['data']:
                    print(sData['title'])
                    hvFile = sData['table'] + "." + sTable['id']
                    hvTable = sData['table'] + sTable['id']
                    if os.path.exists('{}/{}'.format(hvPath, hvFile)):
                        hvdf = pd.read_csv('{}/{}'.format(hvPath, hvFile), sep=" ", header=None)
                        columnsStr, columnsFloat = splitAdministratorData(sTable['parameter']['columnsStr'], sTable['parameter']['columnsFloat'])
                        columns = columnsStr
                        if columnsFloat: columns.extend(columnsFloat)
                        hvdf.columns = columns
                        hvdf[columnsStr] = hvdf[columnsStr].astype(str)
                        hvdf[columnsFloat] = hvdf[columnsFloat].astype(float)
                        itemList = hvdf['storageSystemId'].drop_duplicates().to_list()
                        if itemList: hvList.extend(itemList)
                        if len(columnsStr) > 3:
                            groupByList = columnsStr[0:3]
                        else:
                            groupByList = columnsStr
                        groupBy = ', '.join(map(str, groupByList))
                        hvdf.to_sql(hvTable, hvCon, if_exists = 'append', index = False)
                        for storage in itemList:
                            sqlCommand = 'DELETE FROM "{}" WHERE storageSystemId = "{}" and rowid not in (SELECT min(rowid) FROM "{}" WHERE storageSystemId = "{}" GROUP BY {})'.format(hvTable, storage, hvTable, storage, groupBy)
                            hvCon.execute(sqlCommand)
                            hvCon.commit()
            shutil.rmtree(hvPath)
            os.remove(hvUploadDir + '/' + hvUploadFile)
        hvList = list(dict.fromkeys(hvList))
        if len(hvList) > 1:
            flash('"{}" were successfully added!'.format(', '.join(hvList)))
        else:
            flash('"{}" was successfully added!'.format(', '.join(hvList)))
    except sqlite3.Error as error:
        flash("Error while connecting to sqlite", error)
    finally:
        if (hvCon):
            hvCur.close()
            hvCon.close()

def emptyDb (storageSystemId=None):
    try:
        hvCon = sqlite3.connect('data/db/hv.db') 
        for sData in hvData:
            for sTable in sData['data']:
                if storageSystemId:
                    sqlCommand = 'DELETE FROM "{}{}" WHERE storageSystemId = "{}"'.format(sData['table'], sTable['id'], storageSystemId)
                else:
                    sqlCommand = 'DELETE FROM "{}{}"'.format(sData['table'], sTable['id'])
                hvCon.execute(sqlCommand)
                hvCon.commit()
    except sqlite3.Error as error:
        flash("Error while connecting to sqlite", error)
    finally:
        if (hvCon):
            hvCon.close()

def getDbConnection():
    conn = sqlite3.connect('data/db/hv.db')
    conn.row_factory = sqlite3.Row
    return conn

def deleteJson ():
    now = time.time()
    for f in os.listdir('static/json'):
      if os.stat('static/json/{}'.format(f)).st_mtime < now - 300:
        if os.path.isfile('static/json/{}'.format(f)):
          os.remove('static/json/{}'.format(f))
    threading.Timer(300, deleteJson).start()

def getStorage(storageSystemId):
    conn = getDbConnection()
    storage = conn.execute('SELECT * FROM hvStorages1 WHERE storageSystemId = {} ORDER BY storageSystemId DESC LIMIT 1'.format(storageSystemId)).fetchone()
    conn.close()
    if storage is None:
        abort(404)
    return storage

def splitAdministratorData(columnsStr, columnsFloat):
    editedColStr = [i.split('.', -2)[0] for i in columnsStr]
    editedColFloat = []
    for item in columnsFloat:
        if 'InBytes' in item: item = item.split('InBytes')[0]
        if '.' in item: item = item.split('.')[-2]
        editedColFloat.append(item)
    return editedColStr, editedColFloat

def getBar(source, hvDev, title):
    if '(GB)' in title:
        dx = 20
    else:
        dx = 10
    if hvDev:
        base = alt.Chart(source, title=title).encode(
            x='value:Q',
            y='metric:O',
            color='metric:N',
        )

        myplot = alt.layer(
            base.mark_bar(),
            base.mark_text(dx=dx).encode(text='value')
        ).properties(
            width=600,
            height=150,
        ).facet(
            row='{}:N'.format(hvDev),
        )
    else:
        base = alt.Chart(source, title=title).mark_bar().encode(
            x='value:Q',
            y="metric:O"
        )
        text = base.mark_text(
            align='left',
            baseline='middle',
            dx=3  
        ).encode(
            text='value:Q',
        )
        myplot = (base + text).properties(
            width=700,
            height=200,
        )
    return myplot


def getPlot(source, hvDev, init, title):
    label = alt.selection(type='single', nearest=True, on='mouseover',
                            fields=['date'], empty='none')

    selection = alt.selection_multi(fields=['variable'], bind='legend')
    brush = alt.selection(type='interval', encodings=['x'])
    if hvDev:
        selectBox = alt.binding_select(options=list(source[hvDev].unique()), name='{}  '.format(hvDev))
        drop = alt.selection_single(name='Select', fields=[hvDev], bind=selectBox, init={hvDev: init})
        base = alt.Chart(source, title=title).mark_line(interpolate='basis').encode(
            x = 'date:T',
            y = 'value:Q',
            color='variable:N',
            opacity=alt.condition(selection, alt.value(1), alt.value(0.2))
        ).transform_filter(
            drop
        )
        myplot = alt.layer(
            base, # base line chart
    
            # add a rule mark to serve as a guide line
            alt.Chart().mark_rule(color='#aaa').encode(
                x='date:T'
            ).transform_filter(label),
    
            # add circle marks for selected time points, hide unselected points
            base.mark_circle().encode(
                opacity=alt.condition(label, alt.value(1), alt.value(0))
            ).add_selection(label),
    
            # add white stroked text to provide a legible background for labels
            base.mark_text(align='left', dx=5, dy=-5, stroke='white', strokeWidth=4).encode(
                text='value:Q'
            ).transform_filter(label),
    
            # add text labels for stock prices
            base.mark_text(align='left', dx=5, dy=-5).encode(
                text='value:Q'
            ).transform_filter(label)
        ).add_selection(
            selection, drop
        ).properties(
            width=800,
            height=300,
            description=title
        )
    else:
        base = alt.Chart(source, title=title).mark_line(interpolate='basis').encode(
            x='date:T',
            y='value:Q',
            color='variable:N',
            opacity=alt.condition(selection, alt.value(1), alt.value(0.2))
        )
        myplot = alt.layer(
            base, # base line chart

            # add a rule mark to serve as a guide line
            alt.Chart().mark_rule(color='#aaa').encode(
                x='date:T'
            ).transform_filter(label),

            # add circle marks for selected time points, hide unselected points
            base.mark_circle().encode(
                opacity=alt.condition(label, alt.value(1), alt.value(0))
            ).add_selection(label),

            # add white stroked text to provide a legible background for labels
            base.mark_text(align='left', dx=5, dy=-5, stroke='white', strokeWidth=4).encode(
                text='value:Q'
            ).transform_filter(label),

            # add text labels for stock prices
            base.mark_text(align='left', dx=5, dy=-5).encode(
                text='value:Q'
            ).transform_filter(label)
        ).add_selection(
            selection
        ).properties(
            width=800,
            height=300,
            description=title
        )
    return myplot

def jsonDir(data, data_dir='static/json'):
    return pipe(data, alt.to_json(filename=data_dir + '/{prefix}-{hash}.{extension}') )

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'data/tmp'
app.config['UPLOAD_EXTENSIONS'] = ['.zip']
app.config['DROPZONE_UPLOAD_MULTIPLE'] = True
app.config['SECRET_KEY'] = 'hv209@dnmduf8!23jQa'
alt.renderers.enable('default')
alt.data_transformers.disable_max_rows()
#alt.data_transformers.enable('data_server')
alt.data_transformers.register('jsonDir', jsonDir)
alt.data_transformers.enable('jsonDir', data_dir='static/json')

try:
    with open('conf/hvData.json') as dataFile:
        hvData = json.load(dataFile)
    dataFile.close()
except:
    flash('hvData.json definition file does not exist!')
    exit(1)

os.makedirs('data', exist_ok=True)
os.makedirs('data/db', exist_ok=True)
os.makedirs('data/tmp', exist_ok=True)
os.makedirs('static/json', exist_ok=True)
deleteJson()

if not os.path.isfile('data/db/hv.db'):
    initializeDb()

@app.route('/')
def index(sort='storageSystemId'):
    if 'sort' in request.args:
        sort = request.args['sort']
        request.args.clear
    conn = getDbConnection()
    storages = conn.execute('SELECT storageSystemId, model, max(date) as latest FROM "hvStorages1" group by storageSystemId ORDER by {}'.format(sort)).fetchall()
    conn.close()
    return render_template('index.html', storages=storages)
    
@app.route('/', methods=['POST'])
def uploadFiles():
    storageList = []
    uploadedFiles = request.files.getlist("file")
    for uploadedFile in uploadedFiles:
        fileName = secure_filename(uploadedFile.filename)
        if fileName != '':
            fileExt = os.path.splitext(fileName)[1]
            if fileExt in app.config['UPLOAD_EXTENSIONS']:
                uploadedFile.save(os.path.join(app.config['UPLOAD_FOLDER'], fileName))
                storageList.append(fileName)
    
    updateThread = AppContextThread(target=updateDb(storageList, app.config['UPLOAD_FOLDER']))
    updateThread.start()
    updateThread.join()
    return redirect(url_for('index'))
    
@app.route('/<int:storageSystemId>', methods=('GET', 'POST'))
def post(storageSystemId):
    storage = getStorage(storageSystemId)
    conn = sqlite3.connect('data/db/hv.db')
    df = pd.read_sql_query('SELECT * FROM "hvCache1" WHERE storageSystemId = "{}"'.format(storageSystemId), conn)
    df['date'] = pd.to_datetime(df['date'])
    datedf = df['date'].dt.date.drop_duplicates()
    datedf = pd.DataFrame({'date':datedf.values})
    datedf = datedf.sort_values(by="date")
    datedf['date'] = pd.to_datetime(datedf['date'])
    datedf['date'] = (datedf['date'] - datetime(1970,1,1)).dt.total_seconds() * 1000
    values = datedf['date'].tolist()
    values = list(map(int, values))
    startDate = values[-1]
    endDate = startDate + 86400000
    values.append(endDate)
    if request.method == 'POST':
        dateRange = request.form['dateSlider']
        dateRange = dateRange.split(';')
        startDate = dateRange[0]
        endDate = dateRange[1]
    
    sDate = int(int(startDate)/1000)
    sDate = datetime.utcfromtimestamp(sDate).strftime('%Y-%m-%d %H:%M:%S')
    eDate = int(int(endDate)/1000)
    eDate = datetime.utcfromtimestamp(eDate).strftime('%Y-%m-%d %H:%M:%S')

    charts = []
    tables = []
    dvTitles = []
    adTitles = []
    hvInit = ''

    for sData in hvData:
        for sTable in sData['data']:
            dbTable = sData['table'] + sTable['id']
            plotdf = pd.read_sql_query('SELECT * FROM "{}" where storageSystemId="{}" ORDER by date'.format(dbTable, storageSystemId), conn)
            if not plotdf.empty:
                if sData['type'] == 'administrator' and sTable['type'] == 'table':
                    lastDate = plotdf['date'].iloc[-1]
                    plotdf = plotdf[plotdf.date.isin([lastDate])].reset_index(drop=True)
                    if not sTable['title'] in adTitles:
                        adTitles.append(sTable['title'])
                    else:
                        adTitles.append('')
                    if sData['table'] == 'hvParityGroups':
                        stTable = plotdf.sort_values(by=['parityGroupId']).style.set_table_styles([
                                {"selector": "table", "props": "border:1px solid lightgray; width:100%"},
                                {"selector": "tr", "props": "line-height: 20px; border:1px solid lightgray; text-align: left; "},
                                {"selector": "td,th", "props": "line-height: inherit; padding: 1px 20px 1px 0; text-align: left; border:1px solid lightgray;"}]).hide(axis='index').to_html().replace('\n', '')
                    else:
                        plotdf.set_index('storageSystemId',inplace=True)
                        stTable = plotdf.transpose().style.set_table_styles([
                                {"selector": "table", "props": "border:1px solid lightgray; width:100%"},
                                {"selector": "tr", "props": "line-height: 20px; border:1px solid lightgray; text-align: left; "},
                                {"selector": "td,th", "props": "line-height: inherit; padding: 1px 20px 1px 0; text-align: left; border:1px solid lightgray;"}]).to_html().replace('\n', '')
                    tables.append(stTable)
                    #df.set_index('storageSystemId',inplace=True)
                    #df.transpose().style.set_table_styles().to_html()
                elif sData['type'] == 'analyzer' or sTable['type'] == 'plot':
                    if not sTable['title'] in dvTitles:
                        dvTitles.append(sTable['title'])
                    else:
                        dvTitles.append('')
                    if sData['type'] == 'analyzer':
                        plotdf['date'] = pd.to_datetime(plotdf['date'])

                        if len(sTable['parameter']['columnsStr']) > 2:
                            plotdf = plotdf.sort_values([sTable['parameter']['columnsStr'][2], "date"])
                            plotdf = pd.melt(plotdf, id_vars =sTable['parameter']['columnsStr'], value_vars = sTable['parameter']['columnsFloat'])
                            hvInit = plotdf.sort_values(sTable['parameter']['columnsStr'][2])[sTable['parameter']['columnsStr'][2]].unique()[0]
                            hvDev = sTable['parameter']['columnsStr'][2]
                        else:
                            plotdf = pd.melt(plotdf, id_vars =sTable['parameter']['columnsStr'], value_vars = sTable['parameter']['columnsFloat'])
                            hvDev = None
            
                        mask = (plotdf['date'] > sDate) & (plotdf['date'] <= eDate)
                        plotdf = plotdf.loc[mask]
                        chart = getPlot(plotdf, hvDev, hvInit, sTable['title'])
                        chart = chart.to_json().replace("\n", "").replace("\t","")
                        charts.append(chart)
                    else:
                        adminColStr, adminColFloat = splitAdministratorData(sTable['parameter']['columnsStr'], sTable['parameter']['columnsFloat'])
                        if '(GB)' in sTable['title']:
                            plotdf[adminColFloat] = plotdf[adminColFloat].astype(int)
                        plotdf = pd.melt(plotdf, id_vars = adminColStr, value_vars = adminColFloat)
                        plotdf = plotdf.rename(columns = {'variable':'metric'})
                        if len(adminColStr) > 2:
                            chart = getBar(plotdf, adminColStr[2], sTable['title'])
                        else:
                            chart = getBar(plotdf, None, sTable['title'])
                        chart = chart.to_json().replace("\n", "").replace("\t","")
                        charts.append(chart)
        
    conn.close()
    return render_template('post.html', storage=storage, values=values, start=startDate, end=endDate, charts=charts, dvtitles=dvTitles, tables=tables, adtitles=adTitles)

@app.route('/<int:storageSystemId>/deleteStorage')
def deleteStorage(storageSystemId):
    dateRange = 'all'
    emptyDb(storageSystemId)
    return redirect(url_for('index'))

@app.route('/deleteAll')
def deleteAll():
    emptyDb()
    return redirect(url_for('index'))

@app.route('/sortBySerial')
def sortBySerial():
    return redirect(url_for('index', sort='storageSystemId, model'))

@app.route('/sortbyModel')
def sortbyModel():
    return redirect(url_for('index', sort='model, storageSystemId'))

@app.route('/sortbyDate')
def sortByDate():
    return redirect(url_for('index', sort='date, storageSystemId'))

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    app.run(debug=True)

