#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Aug 20 14:29:14 2021

@author: Jérémy Bernard, University of Gothenburg
"""

from GlobalVariables import *
import DataUtil

def loadData(inputGeometries                , prefix,
             idFieldBuild                   , buildingHeightField,
             vegetationBaseHeight           , vegetationTopHeight,
             idVegetation                   , vegetationAttenuationFactor,
             cursor):
    """ Load the input files into the database (could be converted if from CAD)
    
		Parameters
		_ _ _ _ _ _ _ _ _ _ 
        
            inputGeometries: Dictionary
                Contains the type of geometry to load and the associated file name
            prefix: String
                Name of the case to run. Also the name of the subdirectory containing
                the geometry files.
            idFieldBuild: String
                Name of the ID field from the input building data
            buildingHeightField: String
                Name of the height field from the input building data
            vegetationBaseHeight: String
                Name of the base height field from the input vegetation data
            vegetationTopHeight: String
                Name of the top height field from the input vegetation data
            idVegetation: String
                Name of the ID field from the input vegetation data
            vegetationAttenuationFactor: String
                Name of the attenuatiojn factor field from the input vegetation data
            cursor: conn.cursor
                A cursor object, used to perform spatial SQL queries
            
		Returns
		_ _ _ _ _ _ _ _ _ _ 

            None"""
    print("Load input data")
    inputDataRel = {}
    inputDataAbs = {}
    # Check if the input comes from CAD file
    if inputGeometries["cadTriangles"]:
        # IMPORT TRIANGLES AND CONVERT TO BUILDINGS AND VEGETATION GEOMETRIES
        inputDataRel["cadTriangles"] = os.path.join(INPUT_DIRECTORY, prefix, 
                                                    inputGeometries["cadTriangles"])
        inputDataAbs["cadTriangles"] = os.path.abspath(inputDataRel["cadTriangles"])        
        
        # Load CAD triangles into H2GIS DB
        loadFile(cursor = cursor,
                 filePath = inputDataAbs["cadTriangles"], 
                 tableName = CAD_TRIANGLE_NAME)
        
        if inputGeometries["cadTreesIntersection"]:
            inputDataRel["cadTreesIntersection"] = os.path.join(INPUT_DIRECTORY, prefix, 
                                                                inputGeometries["cadTreesIntersection"])
            inputDataAbs["cadTreesIntersection"] = os.path.abspath(inputDataRel["cadTreesIntersection"])        
            
            # Load vegetation intersection into H2GIS DB
            loadFile(cursor = cursor,
                     filePath = inputDataAbs["cadTreesIntersection"], 
                     tableName = CAD_VEG_INTERSECTION)
            treesZone = CAD_VEG_INTERSECTION
        else:
            cursor.execute("""
                DROP TABLE IF EXISTS {0};
                CREATE TABLE {0}(PK INTEGER, {1} GEOMETRY,
                                 {2} DOUBLE, {3} DOUBLE,
                                 {4} INTEGER, {5} DOUBLE)
                """.format( VEGETATION_TABLE_NAME,
                            GEOM_FIELD,
                            VEGETATION_CROWN_BASE_HEIGHT,
                            VEGETATION_CROWN_TOP_HEIGHT,
                            ID_VEGETATION,
                            VEGETATION_ATTENUATION_FACTOR))
            treesZone = None
        
        # Convert 3D triangles to 2.5 d buildings and tree patches
        fromShp3dTo2_5(cursor = cursor, triangles3d = CAD_TRIANGLE_NAME,
                       TreesZone = treesZone, prefix = PREFIX_NAME)
        
    else:
        # 1. IMPORT BUILDING GEOMETRIES
        inputDataRel["buildings"] = os.path.join(INPUT_DIRECTORY, prefix, 
                                                 inputGeometries["buildingFileName"])
        inputDataAbs["buildings"] = os.path.abspath(inputDataRel["buildings"])
        
        # Load buildings into H2GIS DB
        loadFile(cursor = cursor,
                 filePath = inputDataAbs["buildings"], 
                 tableName = BUILDING_TABLE_NAME)
        
        # Rename building fields to generic names
        importQuery = """
            ALTER TABLE {0} RENAME COLUMN {1} TO {2};
            ALTER TABLE {0} RENAME COLUMN {3} TO {4};
            """.format( BUILDING_TABLE_NAME,
                        idFieldBuild, ID_FIELD_BUILD,
                        buildingHeightField, HEIGHT_FIELD)
        
        # 2. IMPORT VEGETATION GEOMETRIES
        if inputGeometries["vegetationFileName"]:
            inputDataRel["vegetation"] = os.path.join(INPUT_DIRECTORY, prefix, 
                                                      inputGeometries["vegetationFileName"])
            inputDataAbs["vegetation"] = os.path.abspath(inputDataRel["vegetation"])

            # Load buildings into H2GIS DB
            loadFile(cursor = cursor,
                     filePath = inputDataAbs["vegetation"], 
                     tableName = VEGETATION_TABLE_NAME)
            # Load vegetation data and rename fields to generic names
            importQuery += """
                ALTER TABLE {0} RENAME COLUMN {1} TO {2};
                ALTER TABLE {0} RENAME COLUMN {3} TO {4};
                ALTER TABLE {0} RENAME COLUMN {5} TO {6};
                ALTER TABLE {0} RENAME COLUMN {7} TO {8};
                """.format( VEGETATION_TABLE_NAME,
                            vegetationBaseHeight, VEGETATION_CROWN_BASE_HEIGHT,
                            vegetationTopHeight, VEGETATION_CROWN_TOP_HEIGHT,
                            idVegetation, ID_VEGETATION,
                            vegetationAttenuationFactor, VEGETATION_ATTENUATION_FACTOR)
        else:
            importQuery += """ DROP TABLE IF EXISTS {0};
                               CREATE TABLE {0}(PK INTEGER, {1} GEOMETRY,
                                                {2} DOUBLE, {3} DOUBLE,
                                                {4} INTEGER, {5} DOUBLE)
                            """.format( VEGETATION_TABLE_NAME,
                                        GEOM_FIELD,
                                        VEGETATION_CROWN_BASE_HEIGHT,
                                        VEGETATION_CROWN_TOP_HEIGHT,
                                        ID_VEGETATION,
                                        VEGETATION_ATTENUATION_FACTOR)
        cursor.execute(importQuery)
    
def loadFile(cursor, filePath, tableName):
    """ Load a file in the database according to its extension
    
		Parameters
		_ _ _ _ _ _ _ _ _ _ 

            cursor: conn.cursor
                A cursor object, used to perform spatial SQL queries
            filePath: String
                Path of the file to load
            tableName: String
                Name of the table for the loaded file
            
		Returns
		_ _ _ _ _ _ _ _ _ _ 

            None"""
    print("Load table '{0}'".format(tableName))    

    # Get the input building file extension and the appropriate h2gis read function name
    fileExtension = filePath.split(".")[-1]
    readFunction = DataUtil.readFunction(fileExtension)
    
    #Load buildings into H2GIS DB and rename fields to generic names
    cursor.execute("""
       DROP TABLE IF EXISTS {0};
        CALL {2}('{1}','{0}');
        """.format( tableName, filePath,readFunction))

def fromShp3dTo2_5(cursor, triangles3d, TreesZone, prefix = PREFIX_NAME, 
                   save = True):
    """ Convert 3D shapefile to 2.5 D shapefiles distinguishing
    buildings from trees if the surface intersecting trees is passed
    
		Parameters
		_ _ _ _ _ _ _ _ _ _ 

            cursor: conn.cursor
                A cursor object, used to perform spatial SQL queries
            triangles3d: String
                Name of the table containing the 3D geometries from the CAD
            TreesZone: String
                Name of the table containing the zones intersecting trees triangles
            prefix: String, default PREFIX_NAME
                Prefix to add to the output table name
            save: boolean, default True
                Whether or not the resulting 2.5 layers are saved
            
		Returns
		_ _ _ _ _ _ _ _ _ _ 

            None"""
    print("From 3D to 2.5D geometries")
    
    # Create temporary table names (for tables that will be removed at the end of the IProcess)
    trianglesWithId = DataUtil.postfix("triangles_with_id")
    trees2d = DataUtil.postfix("trees_2d")
    buildings2d = DataUtil.postfix("buildings_2d")
    treesCovered = DataUtil.postfix("trees_covered")
    buildingsCovered = DataUtil.postfix("buildings_covered")

    # Add ID to the input data and remove vertical polygons...
    cursor.execute("""
       DROP TABLE IF EXISTS {0}; 
       CREATE TABLE {0}(ID SERIAL, {1} GEOMETRY) 
            AS (SELECT NULL, {1} 
                FROM ST_EXPLODE('(SELECT * FROM {2} WHERE ST_AREA({1})>0)'))
            """.format(trianglesWithId, GEOM_FIELD, triangles3d))
    
    if TreesZone:
        # Identify triangles being trees and convert them to 2D polygons
        cursor.execute("""
           {6};
           {7};
           DROP TABLE IF EXISTS {0};
           CREATE TABLE {0} 
                AS SELECT   a.ID, ST_FORCE2D(a.{1}) AS {1}, 
                            CAST(ST_ZMAX(a.{1}) AS INT) AS {2},
                            CAST(ST_ZMIN(a.{1}) AS INT) AS {3}
                FROM    {4} AS a, {5} AS b
                WHERE   a.{1} && b.{1} AND ST_INTERSECTS(a.{1}, b.{1})
                """.format( trees2d                             , GEOM_FIELD,
                            VEGETATION_CROWN_TOP_HEIGHT         , VEGETATION_CROWN_BASE_HEIGHT,
                            trianglesWithId                     , TreesZone,
                            DataUtil.createIndex(tableName=trianglesWithId, 
                                                fieldName=GEOM_FIELD,
                                                isSpatial=True),
                            DataUtil.createIndex(tableName=TreesZone, 
                                                fieldName=GEOM_FIELD,
                                                isSpatial=True)))
        
        # Identify triangles being buildings and convert them to 2D polygons
        cursor.execute("""
            {5};
            {6};
            DROP TABLE IF EXISTS {0};
            CREATE TABLE {0} 
                AS SELECT   a.ID, ST_FORCE2D(a.{1}) AS {1},
                            CAST(ST_ZMAX(a.{1}) AS INT) AS {2}
                FROM    {3} AS a LEFT JOIN {4} AS b
                ON      a.ID = b.ID
                WHERE   b.ID IS NULL
                """.format( buildings2d         , GEOM_FIELD,
                            HEIGHT_FIELD        , trianglesWithId,
                            trees2d             , DataUtil.createIndex( tableName=trianglesWithId, 
                                                                        fieldName="ID",
                                                                        isSpatial=False),
                            DataUtil.createIndex(tableName=trees2d, 
                                                 fieldName="ID",
                                                 isSpatial=False)))

        # Identify unique trees triangles keeping only the highest one whenever 
        # 2 triangles are superimposed
        cursor.execute("""
            {9};
            {10};
            {11};
            DROP TABLE IF EXISTS {0};
            CREATE TABLE {0} 
                AS SELECT   b.ID AS ID
                FROM    {3} AS a, {3} AS b
                WHERE   a.{1} && b.{1} AND 
                        (ST_COVERS(a.{1}, b.{1}) AND a.{2} > b.{2} OR
                        ST_EQUALS(a.{1}, b.{1}) AND a.{2} = b.{2} AND a.ID < b.ID)
                GROUP BY b.ID;
           CREATE INDEX IF NOT EXISTS id_ID_{0} ON {0}(ID);   
           DROP TABLE IF EXISTS {4};
           CREATE TABLE {4}
               AS SELECT    a.ID AS {5}, a.{1}, a.{2}, 0 AS {6}, {7} AS {8}
               FROM         {3} AS a LEFT JOIN {0} AS b
                            ON a.ID = b.ID
           WHERE    b.ID IS NULL
            """.format( treesCovered                    , GEOM_FIELD,
                        VEGETATION_CROWN_TOP_HEIGHT     , trees2d,
                        VEGETATION_TABLE_NAME           , ID_VEGETATION,
                        VEGETATION_CROWN_BASE_HEIGHT    , DEFAULT_VEG_ATTEN_FACT,
                        VEGETATION_ATTENUATION_FACTOR   , DataUtil.createIndex(tableName=trees2d, 
                                                                               fieldName=GEOM_FIELD,
                                                                               isSpatial=True),
                        DataUtil.createIndex(tableName=trees2d, 
                                             fieldName=VEGETATION_CROWN_TOP_HEIGHT,
                                             isSpatial=False),
                        DataUtil.createIndex(tableName=trees2d, 
                                             fieldName="ID",
                                             isSpatial=False)))
    
    else:
        # Convert building triangles to to 2.5D polygons
        cursor.execute("""
           DROP TABLE IF EXISTS {0};
           CREATE TABLE {0} 
                AS SELECT   ID, ST_FORCE2D({1}) AS {1}, 
                            CAST(ST_ZMAX({1}) AS INT) AS {2}
                FROM    {3}
                """.format( buildings2d         , GEOM_FIELD,
                            HEIGHT_FIELD        , trianglesWithId))
    
    # Identify unique building triangles keeping only the highest one whenever 
    # 2 triangles are superimposed
    cursor.execute("""
        {6};
        {7};
        {8};
        DROP TABLE IF EXISTS {0};
        CREATE TABLE {0} 
            AS SELECT   b.ID AS ID
            FROM    {3} AS a, {3} AS b
            WHERE   a.{1} && b.{1} AND ST_COVERS(a.{1}, b.{1}) AND
                    (ST_COVERS(a.{1}, b.{1}) AND a.{2} > b.{2} OR
                    ST_EQUALS(a.{1}, b.{1}) AND a.{2} = b.{2} AND a.ID < b.ID)
            GROUP BY b.ID;
        {9};   
        DROP TABLE IF EXISTS {4};
        CREATE TABLE {4}
            AS SELECT    a.ID AS {5}, a.{1}, a.{2} 
            FROM         {3} AS a LEFT JOIN {0} AS b
                         ON a.ID = b.ID
        WHERE    b.ID IS NULL
            """.format( buildingsCovered        , GEOM_FIELD,
                        HEIGHT_FIELD            , buildings2d,
                        BUILDING_TABLE_NAME     , ID_FIELD_BUILD,
                        DataUtil.createIndex(tableName=buildings2d, 
                                             fieldName="ID",
                                             isSpatial=False),
                        DataUtil.createIndex(tableName=buildings2d, 
                                             fieldName=GEOM_FIELD,
                                             isSpatial=True),
                        DataUtil.createIndex(tableName=buildings2d, 
                                             fieldName=HEIGHT_FIELD,
                                             isSpatial=False),
                        DataUtil.createIndex(tableName=buildingsCovered, 
                                             fieldName="ID",
                                             isSpatial=False)))

    if not DEBUG:
        # Drop intermediate tables
        cursor.execute("DROP TABLE IF EXISTS {0}".format(",".join([trianglesWithId,
                                                                   trees2d,
                                                                   buildings2d])))