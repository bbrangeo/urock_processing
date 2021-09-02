#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jan 25 15:27:25 2021

@author: Jérémy Bernard, University of Gothenburg
"""
import DataUtil as DataUtil
import pandas as pd
from GlobalVariables import *

def displacementZones(cursor, upwindTable, zonePropertiesTable, srid,
                      prefix = PREFIX_NAME):
    """ Creates the displacement zone and the displacement vortex zone
    for each of the building upwind facade based on Kaplan et Dinar (1996)
    for the equations of the ellipsoid 
        - Equation 2 when the facade is perpendicular to the wind,
        - Figure 2 and Table 1 when the facade has an angle Theta with the wind.
    Note that the displacement vortex zone is only calculated is the facade is 
    nearly perpendicular to wind direction.
    
    Obstacle length and width in the equations are given in an input table.
    Note that we strongly recommand to use the 'CalculatesIndicators.zoneProperties' function
    to calculate effective length and width instead of maximum length and width...

    References:
       Kaplan, H., et N. Dinar. « A Lagrangian Dispersion Model for Calculating
       Concentration Distribution within a Built-up Domain ». Atmospheric 
       Environment 30, nᵒ 24 (1 décembre 1996): 4197‑4207.
       https://doi.org/10.1016/1352-2310(96)00144-6.


		Parameters
		_ _ _ _ _ _ _ _ _ _ 

            cursor: conn.cursor
                A cursor object, used to perform spatial SQL queries
            upwindTable: String
                Name of the table containing upwind segment geometries
                (and also the ID of each stacked obstacle)
            zonePropertiesTable: String
                Name of the table containing obstacle zone properties
                (and also the ID of each stacked obstacle)
            srid: int
                SRID of the building data (useful for zone calculation)
            prefix: String, default PREFIX_NAME
                Prefix to add to the output table name
            
		Returns
		_ _ _ _ _ _ _ _ _ _ 

            displacementZonesTable: String
                Name of the table containing the displacement zones
            displacementVortexZonesTable: String
                Name of the table containing the displacement vortex zones"""
    print("Creates displacement zones")
    
    # Output base name
    outputBaseDispName = "DISPLACEMENT_ZONES"
    outputBaseDispVortexName = "DISPLACEMENT_VORTEX_ZONES"
    
    # Name of the output table
    displacementZonesTable = DataUtil.prefix(outputBaseDispName,
                                             prefix = prefix)
    displacementVortexZonesTable = DataUtil.prefix(outputBaseDispVortexName, 
                                                   prefix = prefix)
    
    # Separate the query into two almost similar queries having only
    # different case when conditions and ellipse size
    partOfQueryThatDiffer = pd.DataFrame({
        "where": [" b.{0}*SIN(a.{1})*SIN(a.{1})>{2}".format(DISPLACEMENT_LENGTH_FIELD,
                                                            UPWIND_FACADE_ANGLE_FIELD,
                                                            ELLIPSOID_MIN_LENGTH),
                  " a.{0}>RADIANS(90-{1}) AND a.{0}<RADIANS(90+{1}) ".format(UPWIND_FACADE_ANGLE_FIELD,
                                                               PERPENDICULAR_THRESHOLD_ANGLE)],
        "length": [DISPLACEMENT_LENGTH_FIELD,
                   DISPLACEMENT_LENGTH_VORTEX_FIELD],
        "table": [displacementZonesTable,
                  displacementVortexZonesTable]},
        index = ["displacement", "vortex"])
    query = ["""
        {12};
        {13};
        DROP TABLE IF EXISTS {0};
        CREATE TABLE {0}
            AS SELECT   {1},
                        ST_SETSRID({2}, {14}) AS {2},
                        {3},
                        {4},
                        {8}
            FROM ST_EXPLODE('(SELECT ST_SPLIT(ST_SNAP(ST_ROTATE(ST_SETSRID(ST_MAKEELLIPSE(ST_CENTROID(a.{2}),
                                                                                            ST_LENGTH(a.{2}),
                                                                                            2*b.{5}*SIN(a.{4})*SIN(a.{4})),
                                                                            {14}),
                                                                0.5*PI()-a.{4}),
                                                     a.{2},
                                                     {10}),
                                             a.{2}) AS {2},
                                     a.{1},
                                     b.{3},
                                     a.{4},
                                     a.{8},
                                     ST_LENGTH(a.{2})/2 AS R_x,
                                     b.{5}*SIN(a.{4})*SIN(a.{4}) AS R_y
                             FROM {6} AS a LEFT JOIN {7} AS b ON a.{8} = b.{8}
                             WHERE {9})')
             WHERE      {4}>=0.5*PI()
                            -0.5*PI()+ACOS((1-COS(2*PI()/{11}))*R_x
                                  /SQRT(POWER((1-COS(2*PI()/{11}))*R_x,2)
                                        +POWER(SIN(2*PI()/{11})*R_y,2)))
                   AND EXPLOD_ID = 2 
                   OR   {4}<0.5*PI()
                            -0.5*PI()+ACOS((1-COS(2*PI()/{11}))*R_x
                                  /SQRT(POWER((1-COS(2*PI()/{11}))*R_x,2)
                                        +POWER(SIN(2*PI()/{11})*R_y,2)))
                   AND EXPLOD_ID = 1
           """.format(partOfQueryThatDiffer.loc[zone, "table"]  , UPWIND_FACADE_FIELD,
                       GEOM_FIELD                               , HEIGHT_FIELD,
                       UPWIND_FACADE_ANGLE_FIELD                , partOfQueryThatDiffer.loc[zone, "length"],
                       upwindTable                              , zonePropertiesTable,
                       ID_FIELD_STACKED_BLOCK                   , partOfQueryThatDiffer.loc[zone, "where"],
                       SNAPPING_TOLERANCE                       , NPOINTS_ELLIPSE,
                       DataUtil.createIndex(tableName=upwindTable, 
                                            fieldName=ID_FIELD_STACKED_BLOCK,
                                            isSpatial=False),
                       DataUtil.createIndex(tableName=zonePropertiesTable, 
                                            fieldName=ID_FIELD_STACKED_BLOCK,
                                            isSpatial=False),
                       srid)
                 for zone in partOfQueryThatDiffer.index]
    cursor.execute(";".join(query))
    
    return displacementZonesTable, displacementVortexZonesTable

def cavityAndWakeZones(cursor, zonePropertiesTable, srid,
                       prefix = PREFIX_NAME):
    """ Creates the cavity and wake zones for each of the stacked building
    based on Kaplan et Dinar (1996) for the equations of the ellipsoid 
    (Equation 3). When the building has a non rectangular shape or is not
    perpendicular to the wind direction, use the principles of Figure 1
    in Nelson et al. (2008): the extreme south of the geometry is used
    as center of the ellipse and the ellipse is merged with the envelope 
    of the geometry.
    
    Obstacle length and width in the equations are given in an input table.
    Note that we strongly recommand to use the 'calculatesZoneLength' function
    to calculate effective length and width instead of maximum length and width...

    References:
            Kaplan, H., et N. Dinar. « A Lagrangian Dispersion Model for Calculating
        Concentration Distribution within a Built-up Domain ». Atmospheric 
        Environment 30, nᵒ 24 (1 décembre 1996): 4197‑4207.
        https://doi.org/10.1016/1352-2310(96)00144-6.
           Nelson, Matthew, Bhagirath Addepalli, Fawn Hornsby, Akshay Gowardhan, 
        Eric Pardyjak, et Michael Brown. « 5.2 Improvements to a Fast-Response 
        Urban Wind Model », 2008.


		Parameters
		_ _ _ _ _ _ _ _ _ _ 

            cursor: conn.cursor
                A cursor object, used to perform spatial SQL queries
            zonePropertiesTable: String
                Name of the table stacked obstacle geometries and zone properties
            srid: int
                SRID of the building data (useful for zone calculation)
            prefix: String, default PREFIX_NAME
                Prefix to add to the output table name
            
		Returns
		_ _ _ _ _ _ _ _ _ _ 

            cavityZonesTable: String
                Name of the table containing the cavity zones
            wakeZonesTable: String
                Name of the table containing the wake zones"""
    print("Creates cavity and wake zones")
    
    # Output base name
    outputBaseNameCavity = "CAVITY_ZONES"
    outputBaseNameWake = "WAKE_ZONES"
    
    # Name of the output tables
    cavityZonesTable = DataUtil.prefix(outputBaseNameCavity, prefix = prefix)
    wakeZonesTable = DataUtil.prefix(outputBaseNameWake, prefix = prefix)
        
    
    # Queries for the cavity zones
    queryCavity = """
        DROP TABLE IF EXISTS {0};
        CREATE TABLE {0}
            AS SELECT   {1},
                        ST_SETSRID({2}, {7}) AS {2},
                        {3}
            FROM ST_EXPLODE('(SELECT ST_SPLIT(ST_SNAP(ST_UNION(ST_SETSRID(ST_MAKEELLIPSE(ST_MAKEPOINT((ST_XMIN(ST_ENVELOPE({2}))+
                                                                                                        ST_XMAX(ST_ENVELOPE({2})))/2,
                                                                                                        ST_YMIN(ST_ENVELOPE({2}))),
                                                                                        ST_XMAX(ST_ENVELOPE({2}))-ST_XMIN(ST_ENVELOPE({2})),
                                                                                        2*{4}),
                                                                             {7}),
                                                                 ST_ENVELOPE({2})),
                                                     ST_ENVELOPE({2}),
                                                     {6}),
                                             ST_GeometryN(ST_TOMULTILINE({2}),1)) AS {2},
                                     {1},
                                     {3}
                             FROM {5})')
             WHERE EXPLOD_ID = 1
                     
           """.format(cavityZonesTable                  , ID_FIELD_STACKED_BLOCK,
                       GEOM_FIELD                       , HEIGHT_FIELD,
                       CAVITY_LENGTH_FIELD              , zonePropertiesTable,
                       SNAPPING_TOLERANCE               , srid)
    cursor.execute(queryCavity)
    
    # Queries for the wake zones
    queryWake = """
        DROP TABLE IF EXISTS {0};
        CREATE TABLE {0}
            AS SELECT   {1},
                        ST_SETSRID({2}, {7}) AS {2},
                        {3}
            FROM ST_EXPLODE('(SELECT ST_SPLIT(ST_SNAP(ST_UNION(ST_SETSRID(ST_MAKEELLIPSE(ST_MAKEPOINT((ST_XMIN(ST_ENVELOPE({2}))+
                                                                                                    ST_XMAX(ST_ENVELOPE({2})))/2,
                                                                                                    ST_YMIN(ST_ENVELOPE({2}))),
                                                                                        ST_XMAX(ST_ENVELOPE({2}))-ST_XMIN(ST_ENVELOPE({2})),
                                                                                        2*{4}),
                                                                            {7}),
                                                                 ST_ENVELOPE({2})),
                                                     ST_ENVELOPE({2}),
                                                     {6}),
                                             ST_GeometryN(ST_TOMULTILINE({2}),1)) AS {2},
                                     {1},
                                     {3}
                             FROM {5})')
             WHERE EXPLOD_ID = 1
           """.format(wakeZonesTable                    , ID_FIELD_STACKED_BLOCK,
                       GEOM_FIELD                       , HEIGHT_FIELD,
                       WAKE_LENGTH_FIELD                , zonePropertiesTable,
                       SNAPPING_TOLERANCE               , srid)
    cursor.execute(queryWake)    
    
    return cavityZonesTable, wakeZonesTable

def streetCanyonZones(cursor, cavityZonesTable, zonePropertiesTable, upwindTable,
                      srid, prefix = PREFIX_NAME):
    """ Creates the street canyon zones for each of the stacked building
    based on Nelson et al. (2008) Figure 8b. The method is slightly different
    since we use the cavity zone instead of the Lr buffer.

    References:
           Nelson, Matthew, Bhagirath Addepalli, Fawn Hornsby, Akshay Gowardhan, 
        Eric Pardyjak, et Michael Brown. « 5.2 Improvements to a Fast-Response 
        Urban Wind Model », 2008.


		Parameters
		_ _ _ _ _ _ _ _ _ _ 

            cursor: conn.cursor
                A cursor object, used to perform spatial SQL queries
            cavityZonesTable: String
                Name of the table containing the cavity zones and the ID of
                each stacked obstacle
            zonePropertiesTable: String
                Name of the table containing the geometry, zone length, height
                and ID of each stacked obstacle
            upwindTable: String
                Name of the table containing upwind segment geometries
                (and also the ID of each stacked obstacle)
            srid: int
                SRID of the building data (useful for zone calculation)
            prefix: String, default PREFIX_NAME
                Prefix to add to the output table name
            
		Returns
		_ _ _ _ _ _ _ _ _ _ 

            streetCanyonZoneTable: String
                Name of the table containing the street canyon zones"""
    print("Creates street canyon zones")

    # Output base name
    outputBaseName = "STREETCANYON_ZONE"
    
    # Name of the output tables
    streetCanyonZoneTable = DataUtil.prefix(outputBaseName, prefix = prefix)
    
    # Create temporary table names (for tables that will be removed at the end of the IProcess)
    intersectTable = DataUtil.postfix("intersect_table")
    canyonExtendTable = DataUtil.postfix("canyon_extend_table")
    
    # Identify upwind facades intersected by cavity zones
    intersectionQuery = """
        {11};
        {12};
        DROP TABLE IF EXISTS {0};
        CREATE TABLE {0}
            AS SELECT   b.{1} AS {6},
                        a.{1} AS {7},
                        a.{9},
                        a.{5},
                        a.{8},
                        ST_COLLECTIONEXTRACT(ST_INTERSECTION(a.{2}, b.{2}), 2) AS {2},
                        a.{10}
            FROM {3} AS a, {4} AS b
            WHERE a.{2} && b.{2} AND ST_INTERSECTS(a.{2}, b.{2})
           """.format( intersectTable                   , ID_FIELD_STACKED_BLOCK,
                       GEOM_FIELD                       , upwindTable,
                       cavityZonesTable                 , HEIGHT_FIELD,
                       ID_UPSTREAM_STACKED_BLOCK        , ID_DOWNSTREAM_STACKED_BLOCK,
                       UPWIND_FACADE_ANGLE_FIELD        , BASE_HEIGHT_FIELD,
                       UPWIND_FACADE_FIELD              , DataUtil.createIndex( tableName=upwindTable, 
                                                                                fieldName=GEOM_FIELD,
                                                                                isSpatial=True),
                       DataUtil.createIndex(tableName=cavityZonesTable, 
                                            fieldName=GEOM_FIELD,
                                            isSpatial=True))
    cursor.execute(intersectionQuery)
    
    # Identify street canyon extend
    canyonExtendQuery = """
        {14};
        {15};
        DROP TABLE IF EXISTS {3};
        CREATE TABLE {3}
            AS SELECT   a.{1},
                        a.{9},
                        a.{6} AS {7},
                        b.{6} AS {8},
                        a.{11},
                        a.{12},
                        ST_SETSRID(ST_MAKEPOLYGON(ST_MAKELINE(ST_STARTPOINT(a.{4}),
                    								ST_STARTPOINT(ST_TRANSLATE( a.{4}, 
                                                                            0, 
                                                                            ST_YMAX(b.{4})-ST_YMIN(b.{4})+b.{5})),
                    								ST_ENDPOINT(ST_TRANSLATE(   a.{4},
                                                                            0, 
                                                                            ST_YMAX(b.{4})-ST_YMIN(b.{4})+b.{5})),
                    								ST_TOMULTIPOINT(ST_REVERSE(a.{4})))),
                                   {16}) AS THE_GEOM,
                        a.{13}
            FROM {0} AS a LEFT JOIN {2} AS b ON a.{1} = b.{10}
            WHERE NOT ST_ISEMPTY(a.{4})
           """.format( intersectTable                   , ID_UPSTREAM_STACKED_BLOCK,
                       zonePropertiesTable              , canyonExtendTable,
                       GEOM_FIELD                       , CAVITY_LENGTH_FIELD,
                       HEIGHT_FIELD                     , DOWNSTREAM_HEIGHT_FIELD,
                       UPSTREAM_HEIGHT_FIELD            , ID_DOWNSTREAM_STACKED_BLOCK,
                       ID_FIELD_STACKED_BLOCK           , UPWIND_FACADE_ANGLE_FIELD,
                       BASE_HEIGHT_FIELD                , UPWIND_FACADE_FIELD,
                       DataUtil.createIndex(tableName=intersectTable, 
                                            fieldName=ID_UPSTREAM_STACKED_BLOCK,
                                            isSpatial=False),
                       DataUtil.createIndex(tableName=zonePropertiesTable, 
                                            fieldName=ID_FIELD_STACKED_BLOCK,
                                            isSpatial=False),
                       srid)
    cursor.execute(canyonExtendQuery)
    
    # Creates street canyon zones
    streetCanyonQuery = """
        {15};
        DROP TABLE IF EXISTS {2};
        CREATE TABLE {2}({13} SERIAL,
                         {1} INTEGER,
                         {8} INTEGER,
                         {3} GEOMETRY,
                         {4} INTEGER,
                         {5} INTEGER,
                         {11} DOUBLE,
                         {12} INTEGER,
                         {14} INTEGER)
            AS SELECT   NULL AS {13},
                        {1},
                        {8},
                        ST_SETSRID({3}, {16}) AS {3},
                        {4},
                        {5},
                        {11},
                        {12},
                        {14}
            FROM ST_EXPLODE('(SELECT    a.{1},
                                        a.{8},
                                        ST_SPLIT(ST_PRECISIONREDUCER(a.{3},3),
                                                ST_GeometryN(ST_TOMULTILINE(b.{3}),1)) AS {3},
                                        a.{4},
                                        a.{5},
                                        a.{11},
                                        a.{12},
                                        a.{14}
                            FROM        {0} AS a LEFT JOIN {7} AS b ON a.{1}=b.{9})')
            WHERE EXPLOD_ID = 1
                     
           """.format( canyonExtendTable                , ID_UPSTREAM_STACKED_BLOCK,
                       streetCanyonZoneTable            , GEOM_FIELD,
                       DOWNSTREAM_HEIGHT_FIELD          , UPSTREAM_HEIGHT_FIELD,
                       SNAPPING_TOLERANCE               , zonePropertiesTable,
                       ID_DOWNSTREAM_STACKED_BLOCK      , ID_FIELD_STACKED_BLOCK,
                       MESH_SIZE                        , UPWIND_FACADE_ANGLE_FIELD,
                       BASE_HEIGHT_FIELD                , ID_FIELD_CANYON,
                       UPWIND_FACADE_FIELD              , DataUtil.createIndex( tableName=canyonExtendTable, 
                                                                                fieldName=ID_UPSTREAM_STACKED_BLOCK,
                                                                                isSpatial=False),
                       srid)
    cursor.execute(streetCanyonQuery)
    
    if not DEBUG:
        # Drop intermediate tables
        cursor.execute("DROP TABLE IF EXISTS {0}".format(",".join([intersectTable,
                                                                   canyonExtendTable])))
    
    return streetCanyonZoneTable

def rooftopZones(cursor, upwindTable, zonePropertiesTable,
                 prefix = PREFIX_NAME):
    """ Creates the rooftop zones for each of the upwind facade:
        - recirculation zone if the angle between the wind and the facade is included
        within the range [90-PERPENDICULAR_THRESHOLD_ANGLE, 90+PERPENDICULAR_THRESHOLD_ANGLE].
        See Pol et al. (2006) for more details
        - corner zones if the angle between the wind and the facade is included
        within the range [90-CORNER_THRESHOLD_ANGLE[1], 90-CORNER_THRESHOLD_ANGLE[0]]
        or [90+CORNER_THRESHOLD_ANGLE[0], 90+CORNER_THRESHOLD_ANGLE[1]]. See
        Bagal et al. (2004) for more details
    
    Obstacle length and width in the equations are given in an input table.
    Note that we strongly recommand to use the 'CalculatesIndicators.zoneProperties' function
    to calculate effective length and width instead of maximum length and width...

    References:
            Pol, SU, NL Bagal, B Singh, MJ Brown, et ER Pardyjak. « IMPLEMENTATION 
        OF A ROOFTOP RECIRCULATION PARAMETERIZATION INTO THE QUIC FAST 
        RESPONSE URBAN WIND MODEL », 2006.
            Bagal, NL, B Singh, ER Pardyjak, et MJ Brown. « Implementation of
        rooftop recirculation parameterization into the QUIC fast response urban
        wind model ». In Proc. 5th AMS Urban Environ. Symp. Conf, 2004.

		Parameters
		_ _ _ _ _ _ _ _ _ _ 

            cursor: conn.cursor
                A cursor object, used to perform spatial SQL queries
            upwindTable: String
                Name of the table containing upwind segment geometries
                (and also the ID of each stacked obstacle)
            zonePropertiesTable: String
                Name of the table stacked obstacle geometries and zone properties
            prefix: String, default PREFIX_NAME
                Prefix to add to the output table name
            
		Returns
		_ _ _ _ _ _ _ _ _ _ 

            rooftopPerpendicularZoneTable: String
                Name of the table containing the rooftop perpendicular zones
            rooftopCornerZoneTable: String
                Name of the table containing the rooftop corner zones"""
    print("Creates rooftop zones (perpendicular and corner)")
    
    # Output base name
    outputBaseNameroofPerp = "ROOFTOP_PERP_ZONES"
    outputBaseNameroofCorner = "ROOFTOP_CORNER_ZONES"
    
    # Name of the output tables
    roofPerpZonesTable = DataUtil.prefix(outputBaseNameroofPerp, 
                                         prefix = prefix)
    RoofCornerZonesTable = DataUtil.prefix(outputBaseNameroofCorner, 
                                           prefix = prefix)
        
    # Create temporary table names (for tables that will be removed at the end of the IProcess)
    temporaryRooftopPerp = DataUtil.postfix("temporary_rooftop_perp")
    temporaryRooftopCorner = DataUtil.postfix("temporary_rooftop_corner")
    
    # Creates a dictionary of table names in order to simplify the final query
    dicTableNames = pd.DataFrame({"final": [roofPerpZonesTable, RoofCornerZonesTable],
                                  "temporary": [temporaryRooftopPerp, temporaryRooftopCorner]},
                                 index = ["perp", "corner"])
    
    # Piece of query to get Lcx and Lcy (based on equations 3, 4 and 5 from
    # Bagal et al. 2004 - note that in 4 and 5, we assumed that X and Y had been
    # reverted)
    pieceOfQueryLcCorner = "2*ST_LENGTH({0})*TAN(2.94*EXP(0.0297*ABS(PI()/2-{1})))".format(GEOM_FIELD,
                                                                                           UPWIND_FACADE_ANGLE_FIELD)
    
    # Queries to create temporary rooftop zones (perpendicular and corner)
    queryTempoRooftop = """
        DROP TABLE IF EXISTS {0}, {12};
        CREATE TABLE {0}
            AS SELECT   {1},
                        {2},
                        {4},
                        ABS({6}) AS {14},
                        ST_LENGTH({3}) AS {15},
                        {5},
                        CASE    WHEN {5} < PI()/2
                                THEN ST_MAKEPOLYGON(ST_MAKELINE(ST_ENDPOINT({3}),
                                                                ST_TRANSLATE(ST_STARTPOINT({3}),
                                                                             -{6}*SIN(PI()/2-{5}),
                                                                             {6}*COS(PI()/2-{5})),
                                                                ST_STARTPOINT({3}),
                                                                ST_ENDPOINT({3})))
                                ELSE ST_MAKEPOLYGON(ST_MAKELINE(ST_STARTPOINT({3}),
                                                                ST_ENDPOINT({3}),
                                                                ST_TRANSLATE(ST_ENDPOINT({3}),
                                                                             {6}*SIN({5}-PI()/2),
                                                                             {6}*COS({5}-PI()/2)),
                                                                ST_STARTPOINT({3})))
                                END AS {3}
            FROM {7}
            WHERE   {5} > RADIANS(90-{9}) AND {5} < RADIANS(90-{10})
                    OR {5} > RADIANS(90+{10}) AND {5} < RADIANS(90+{9});
        {16};
        {17};
        CREATE TABLE {12}
            AS SELECT   a.{1},
                        a.{2},
                        a.{4},
                        ST_MAKEPOLYGON(ST_MAKELINE(ST_STARTPOINT(a.{3}),
                                                   ST_TRANSLATE(ST_STARTPOINT(a.{3}),
                                                                0,
                                                                -b.{11}),
                                                   ST_TRANSLATE(ST_ENDPOINT(a.{3}),
                                                                0,
                                                                -b.{11}),
                                                   ST_ENDPOINT(a.{3}),
                                                   ST_STARTPOINT(a.{3}))) AS {3}
            FROM {7} AS a LEFT JOIN {8} AS b ON a.{1} = b.{1} 
            WHERE   a.{5} > RADIANS(90-{13}) AND a.{5} < RADIANS(90+{13})
           """.format( temporaryRooftopCorner           , ID_FIELD_STACKED_BLOCK,
                       UPWIND_FACADE_FIELD              , GEOM_FIELD,
                       HEIGHT_FIELD                     , UPWIND_FACADE_ANGLE_FIELD,
                       pieceOfQueryLcCorner             , upwindTable,
                       zonePropertiesTable              , CORNER_THRESHOLD_ANGLE[1],
                       CORNER_THRESHOLD_ANGLE[0]        , ROOFTOP_PERP_LENGTH,
                       temporaryRooftopPerp             , PERPENDICULAR_THRESHOLD_ANGLE,
                       ROOFTOP_CORNER_LENGTH            , ROOFTOP_CORNER_FACADE_LENGTH,
                       DataUtil.createIndex(tableName=upwindTable, 
                                            fieldName=ID_FIELD_STACKED_BLOCK,
                                            isSpatial=False),
                       DataUtil.createIndex(tableName=zonePropertiesTable, 
                                            fieldName=ID_FIELD_STACKED_BLOCK,
                                            isSpatial=False))
    cursor.execute(queryTempoRooftop)
    
    # Queries to limit the rooftop zones to the rooftop of the stacked block...
    extraFieldToKeep = {"perp": "b.{0}, b.{1},".format(ROOFTOP_PERP_LENGTH,
                                                       ROOFTOP_PERP_HEIGHT), 
                        "corner": "a.{0}, a.{1}, a.{2}, b.{3},".format(ROOFTOP_CORNER_LENGTH,
                                                                 ROOFTOP_CORNER_FACADE_LENGTH,
                                                                 UPWIND_FACADE_ANGLE_FIELD,
                                                                 ROOFTOP_WIND_FACTOR)}
    queryCutRooftop = ["""
        {8};
        {9};
        {10};
        {11};
        DROP TABLE IF EXISTS {0};
        CREATE TABLE {0}
            AS SELECT   a.{1},
                        a.{2},
                        a.{4},
                        {7}
                        ST_INTERSECTION(a.{3}, b.{3}) AS {3}
            FROM {5} AS a LEFT JOIN {6} AS b ON a.{1} = b.{1}
            WHERE a.{3} && b.{3} AND ST_INTERSECTS(a.{3}, b.{3})
           """.format( dicTableNames.loc[typeZone, "final"] , ID_FIELD_STACKED_BLOCK,
                       UPWIND_FACADE_FIELD                  , GEOM_FIELD,
                       HEIGHT_FIELD                         , dicTableNames.loc[typeZone, "temporary"],
                       zonePropertiesTable                  , extraFieldToKeep[typeZone],
                       DataUtil.createIndex(tableName=dicTableNames.loc[typeZone, "temporary"], 
                                            fieldName=GEOM_FIELD,
                                            isSpatial=True),
                       DataUtil.createIndex(tableName=zonePropertiesTable, 
                                            fieldName=GEOM_FIELD,
                                            isSpatial=True),
                       DataUtil.createIndex(tableName=dicTableNames.loc[typeZone, "temporary"], 
                                            fieldName=ID_FIELD_STACKED_BLOCK,
                                            isSpatial=False),
                       DataUtil.createIndex(tableName=zonePropertiesTable, 
                                            fieldName=ID_FIELD_STACKED_BLOCK,
                                            isSpatial=False),
                       SNAPPING_TOLERANCE)
               for typeZone in dicTableNames.index]
    cursor.execute(";".join(queryCutRooftop))
    
    if not DEBUG:
        # Drop intermediate tables
        cursor.execute("DROP TABLE IF EXISTS {0}".format(",".join(dicTableNames["temporary"].values)))
    
    return roofPerpZonesTable, RoofCornerZonesTable


def vegetationZones(cursor, vegetationTable, wakeZonesTable,
                    prefix = PREFIX_NAME):
    """ Identify vegetation zones which are in "built up" areas and those
    being in "open areas". Vegetation is considered in a built up area
    when it intersects with build wake zone.

    References:
            Nelson et al., Evaluation of an urban vegetative canopy scheme 
        and impact on plume dispersion. 2009


		Parameters
		_ _ _ _ _ _ _ _ _ _ 

            cursor: conn.cursor
                A cursor object, used to perform spatial SQL queries
            vegetationTable: String
                Name of the table containing vegetation footprints
            wakeZonesTable: String
                Name of the table containing the wake zones
            prefix: String, default PREFIX_NAME
                Prefix to add to the output table name
            
		Returns
		_ _ _ _ _ _ _ _ _ _ 

            vegetationBuiltZoneTable: String
                Name of the table containing the vegetation zone located in 
                built-up areas
            vegetationOpenZoneTable: String
                Name of the table containing the vegetation zone located in 
                open areas"""
    print("Creates built-up and open vegetation zones")
    
    # Output base name
    outputBaseNameOpen = "OPEN_VEGETATION_ZONES"
    outputBaseNameBuilt = "BUILTUP_VEGETATION_ZONES"
    
    # Name of the output tables
    vegetationOpenZoneTable = DataUtil.prefix(outputBaseNameOpen, 
                                              prefix = prefix)
    vegetationBuiltZoneTable = DataUtil.prefix(outputBaseNameBuilt,
                                               prefix = prefix)
        
    # Create temporary table names (for tables that will be removed at the end of the IProcess)
    temporary_built_vegetation = DataUtil.postfix("temporary_built_vegetation")
    
    # Identify vegetation zones being in building wake zones
    cursor.execute("""
        {10};
        {11};
        DROP TABLE IF EXISTS {7};
        CREATE TABLE {7}
            AS SELECT   ST_INTERSECTION(a.{1}, b.{1}) AS {1},
                        a.{3},
                        a.{4},
                        a.{5},
                        a.{6}
            FROM {0} AS a, {2} AS b
            WHERE a.{1} && b.{1} AND ST_INTERSECTS(a.{1}, b.{1});
        {12};
        DROP TABLE IF EXISTS {8};
        CREATE TABLE {8}({9} SERIAL     , {1} GEOMETRY   , {3} DOUBLE,
                         {4} DOUBLE     , {5} DOUBLE     , {6} INTEGER)
            AS SELECT NULL, {1}, {3}, {4}, {5}, {6}
            FROM ST_EXPLODE('(SELECT    ST_UNION(ST_ACCUM({1})) AS {1},
                                        MIN({3}) AS {3},
                                        MIN({4}) AS {4},
                                        MIN({5}) AS {5},
                                        {6}
                            FROM {7}
                            GROUP BY {6})')
        """.format( vegetationTable                  , GEOM_FIELD,
                    wakeZonesTable                   , VEGETATION_CROWN_BASE_HEIGHT,
                    VEGETATION_CROWN_TOP_HEIGHT      , VEGETATION_ATTENUATION_FACTOR,
                    ID_VEGETATION                    , temporary_built_vegetation,
                    vegetationBuiltZoneTable         , ID_ZONE_VEGETATION,
                    DataUtil.createIndex(tableName=vegetationTable, 
                                            fieldName=GEOM_FIELD,
                                            isSpatial=True),
                    DataUtil.createIndex(tableName=wakeZonesTable, 
                                         fieldName=GEOM_FIELD,
                                         isSpatial=True),
                    DataUtil.createIndex(tableName=temporary_built_vegetation, 
                                         fieldName=ID_VEGETATION,
                                         isSpatial=False)))
    
    # Identify vegetation zones being in open areas
    cursor.execute("""
        {9};
        {10};
        DROP TABLE IF EXISTS {7};
        CREATE TABLE {7}({8} SERIAL     , {1} GEOMETRY   , {3} DOUBLE,
                         {4} DOUBLE     , {5} DOUBLE     , {6} INTEGER)
            AS SELECT   NULL, {1}, {3}, {4}, {5}, {6}
            FROM ST_EXPLODE('(SELECT    COALESCE(ST_DIFFERENCE(a.{1}, b.{1}),
                                                a.{1}) AS {1},
                                        a.{3},
                                        a.{4},
                                        a.{5},
                                        a.{6}
                            FROM {0} AS a LEFT JOIN {2} AS b ON a.{6} = b.{6}
                            WHERE NOT ST_ISEMPTY(COALESCE(ST_DIFFERENCE(a.{1}, b.{1}),
                                                          a.{1})))')
        """.format( vegetationTable                  , GEOM_FIELD,
                    temporary_built_vegetation       , VEGETATION_CROWN_BASE_HEIGHT,
                    VEGETATION_CROWN_TOP_HEIGHT      , VEGETATION_ATTENUATION_FACTOR,
                    ID_VEGETATION                    , vegetationOpenZoneTable,
                    ID_ZONE_VEGETATION               , DataUtil.createIndex( tableName=vegetationTable, 
                                                                             fieldName=ID_VEGETATION,
                                                                             isSpatial=False),
                    DataUtil.createIndex(tableName=temporary_built_vegetation, 
                                         fieldName=ID_VEGETATION,
                                         isSpatial=False)))
    
    if not DEBUG:
        # Drop intermediate tables
        cursor.execute("DROP TABLE IF EXISTS {0}".format(",".join([temporary_built_vegetation])))
    
    return vegetationBuiltZoneTable, vegetationOpenZoneTable
