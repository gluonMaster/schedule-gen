Attribute VB_Name = "Modul1"
Sub CreateSchedulePlanning()
    ' This macro reads data from the "Schedule" sheet and creates a new Excel file
    ' with restructured data according to specifications, then runs a series of command line operations
    
    Dim wbSource As Workbook
    Dim wbTarget As Workbook
    Dim wsSource As Worksheet
    Dim wsTarget As Worksheet
    Dim wsMetadata As Worksheet
    Dim lastRow As Long
    Dim i As Long
    Dim targetRow As Long
    Dim targetPath As String
    Dim targetFileName As String
    Dim roomValue As String
    Dim buildingValue As String
    Dim buildingFirstLetter As String
    Dim shellObj As Object
    Dim cmdPath As String
    Dim waitOnReturn As Boolean
    Dim windowStyle As Integer
    Dim execStatus As Integer
    Dim lastUsedRow As Long
    Dim blockCount As Long
    Dim blockRange As Range
    Dim metadataRow As Long
    Dim blockIndex As Long
    Dim targetColumn As Long
    Dim targetColumnLetter As String
    Dim lessonTypeValue As String
    Dim trialDatesJsonValue As String
    Dim lessonTypeColumn As Long
    Dim trialDatesColumn As Long
    Dim blockIdColumn As Long
    Dim rentalDatesColumn As Long
    Dim sourceLayerColumn As Long
    Dim colorColumn As Long
    Dim blockMetadataColumn As Long
    Dim wsSync As Worksheet
    
    ' Optimize performance
    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual
    Application.EnableEvents = False
    Application.DisplayAlerts = False
    
    ' Set references to source workbook and worksheet
    Set wbSource = ThisWorkbook
    Set wsSource = wbSource.Sheets("Schedule")
    lessonTypeColumn = ScheduleColumn(wsSource, "lesson_type", "")
    trialDatesColumn = ScheduleColumn(wsSource, "trial_dates_json", "")
    ' Old web exports have localized headers at J/K. Optimizer J/K are pauses.
    If lessonTypeColumn = 0 And wsSource.Cells(1, 10).Value <> "" Then
        If LCase$(CStr(wsSource.Cells(1, 10).Value)) <> "pause_before" Then lessonTypeColumn = 10
    End If
    If trialDatesColumn = 0 And lessonTypeColumn = 10 Then trialDatesColumn = 11
    blockIdColumn = ScheduleColumn(wsSource, "block_id", "block_id")
    rentalDatesColumn = ScheduleColumn(wsSource, "rental_dates_json", "rental_dates_json")
    sourceLayerColumn = ScheduleColumn(wsSource, "source_layer", "source_layer")
    colorColumn = ScheduleColumn(wsSource, "color", "color")
    blockMetadataColumn = ScheduleColumn(wsSource, "block_metadata_json", "block_metadata_json")
    
    ' Determine the last row with data in source worksheet
    lastRow = wsSource.Cells(wsSource.Rows.Count, 1).End(xlUp).Row
    
    ' Define target file path and name
    targetPath = wbSource.Path & "\..\..\xlsx_initial\"
    targetFileName = "newpref.xlsx"
    
    ' Create folder if it doesn't exist
    On Error Resume Next
    MkDir targetPath
    On Error GoTo 0
    
    ' Create a new workbook for the target
    Set wbTarget = Workbooks.Add
    
    ' Rename the first sheet to "Plannung"
    Set wsTarget = wbTarget.Sheets(1)
    wsTarget.Name = "Plannung"

    ' Create hidden sheet for service metadata
    Set wsMetadata = wbTarget.Worksheets.Add(After:=wsTarget)
    wsMetadata.Name = "__service_metadata"
    wsMetadata.Cells(1, 1).Value = "section_index"
    wsMetadata.Cells(1, 2).Value = "column_letter"
    wsMetadata.Cells(1, 3).Value = "lesson_type"
    wsMetadata.Cells(1, 4).Value = "trial_dates_json"
    wsMetadata.Cells(1, 5).Value = "block_id"
    wsMetadata.Cells(1, 6).Value = "rental_dates_json"
    wsMetadata.Cells(1, 7).Value = "source_layer"
    wsMetadata.Cells(1, 8).Value = "color"
    wsMetadata.Cells(1, 9).Value = "block_metadata_json"
    wsMetadata.Columns("E:I").NumberFormat = "@"
    ' Copy provenance unchanged, including present blank revision cells.
    ' Do not create a sync sheet for a legacy workbook.
    On Error Resume Next
    Set wsSync = wbSource.Worksheets("__schedule_sync")
    On Error GoTo 0
    If Not wsSync Is Nothing Then
        wsSync.Copy After:=wsMetadata
        wbTarget.Worksheets("__schedule_sync").Visible = xlSheetVeryHidden
    End If
    
    ' 1. Add headers and formatting to the first row
    ' 1a. Add header titles
    wsTarget.Cells(1, 2).Value = "Hauptunterricht"
    wsTarget.Cells(1, 3).Value = "Begleitende Unterricht 1"
    wsTarget.Cells(1, 4).Value = "Begleitende Unterricht 2"
    
    ' 1b. Apply light pink background to header row
    wsTarget.Range("B1:D1").Interior.Color = RGB(255, 230, 230)
    
    ' 1c. Freeze the first row
    ' wsTarget must be activated before .Select; Worksheets.Add above left wsMetadata active
    wsTarget.Activate
    wsTarget.Range("A2").Select
    ActiveWindow.FreezePanes = True
    
    ' Initialize target row counter
    targetRow = 2
    targetColumn = 2
    metadataRow = 2
    blockIndex = 0
    
    ' Process each row of data from source
    For i = 2 To lastRow
        ' All lesson types including trial are now written to Plannung and metadata sheet

        ' Get room and building values
        roomValue = CStr(wsSource.Cells(i, 4).Value)
        buildingValue = CStr(wsSource.Cells(i, 5).Value)
        
        ' Extract the first letter of the building name and convert to uppercase
        If Len(buildingValue) > 0 Then
            buildingFirstLetter = UCase(Left(buildingValue, 1))
        Else
            buildingFirstLetter = ""
        End If
        
        ' Transfer data according to the new structure
        
        ' 1st row of section: Subject
        wsTarget.Cells(targetRow, targetColumn).Value = wsSource.Cells(i, 1).Value
        
        ' 2nd row of section: Group
        wsTarget.Cells(targetRow + 1, targetColumn).Value = wsSource.Cells(i, 2).Value
        
        ' 3rd row of section: Teacher
        wsTarget.Cells(targetRow + 2, targetColumn).Value = wsSource.Cells(i, 3).Value
        
        ' 4th row of section: Room - with building first letter prefix
        ' Format as text to preserve format like "2.09"
        wsTarget.Cells(targetRow + 3, targetColumn).NumberFormat = "@"
        If buildingFirstLetter <> "" And UCase$(Left$(roomValue, 1)) = buildingFirstLetter Then
            wsTarget.Cells(targetRow + 3, targetColumn).Value = roomValue
        Else
            wsTarget.Cells(targetRow + 3, targetColumn).Value = buildingFirstLetter & roomValue
        End If
        
        ' 8th row of section: Building
        wsTarget.Cells(targetRow + 7, targetColumn).Value = buildingValue
        
        ' 9th row of section: Duration
        wsTarget.Cells(targetRow + 8, targetColumn).Value = wsSource.Cells(i, 9).Value
        
        ' 10th row of section: Day of week
        wsTarget.Cells(targetRow + 9, targetColumn).Value = wsSource.Cells(i, 6).Value
        
        ' 11th row of section: Start time
        wsTarget.Cells(targetRow + 10, targetColumn).Value = wsSource.Cells(i, 7).Value

        lessonTypeValue = LCase$(Trim$(ScheduleCell(wsSource, i, lessonTypeColumn)))
        If wsSync Is Nothing And rentalDatesColumn = 0 And LCase$(Trim$(CStr(wsSource.Cells(i, 1).Value))) = "vermietung" Then
            lessonTypeValue = "rental"
        End If
        If LCase$(lessonTypeValue) = "trial" Then
            trialDatesJsonValue = ScheduleCell(wsSource, i, trialDatesColumn)
        Else
            trialDatesJsonValue = ""
        End If

        targetColumnLetter = Replace(wsTarget.Cells(1, targetColumn).Address(False, False), "1", "")
        wsMetadata.Cells(metadataRow, 1).Value = blockIndex
        wsMetadata.Cells(metadataRow, 2).Value = targetColumnLetter
        wsMetadata.Cells(metadataRow, 3).Value = lessonTypeValue
        wsMetadata.Cells(metadataRow, 4).Value = trialDatesJsonValue
        wsMetadata.Cells(metadataRow, 5).Value = ScheduleCell(wsSource, i, blockIdColumn)
        If lessonTypeValue = "rental" Then
            If rentalDatesColumn > 0 Then
                wsMetadata.Cells(metadataRow, 6).Value = ScheduleCell(wsSource, i, rentalDatesColumn)
            Else
                wsMetadata.Cells(metadataRow, 6).Value = ScheduleCell(wsSource, i, trialDatesColumn)
            End If
            ' Rental end is the booking end, never an optimizer window.
            wsTarget.Cells(targetRow + 11, targetColumn).Value = wsSource.Cells(i, 8).Value
        End If
        wsMetadata.Cells(metadataRow, 7).Value = ScheduleCell(wsSource, i, sourceLayerColumn)
        wsMetadata.Cells(metadataRow, 8).Value = ScheduleCell(wsSource, i, colorColumn)
        wsMetadata.Cells(metadataRow, 9).Value = ScheduleCell(wsSource, i, blockMetadataColumn)
        metadataRow = metadataRow + 1
        blockIndex = blockIndex + 1
        
        ' Move to the next section (increment by 14 rows)
        targetRow = targetRow + 14
    Next i

    wsMetadata.Visible = xlSheetVeryHidden
    
    ' Get the last used row for formatting
    lastUsedRow = wsTarget.Cells(wsTarget.Rows.Count, 2).End(xlUp).Row
    
    ' 2. Add row labels to column A
    ' 2a. Create array of labels
    Dim labels As Variant
    labels = Array("Unterricht Name", "Gruppe", "Lehrer", "Kabinett", _
                  "Kabinett alter. 1", "Kabinett alter. 2", "Kabinett alter. 3", _
                  "Gebaude", "Dauer (min)", "Tag", "Seit (Zeit)", "Bis (Zeit)", _
                  "Pause vorher (min)", "Pause danach (min)")
    
    ' Calculate number of blocks needed
    blockCount = WorksheetFunction.Ceiling((lastUsedRow - 1) / 14, 1)
    
    ' Add labels to column A for each block
    For i = 0 To blockCount - 1
        For j = 0 To 13
            wsTarget.Cells(2 + i * 14 + j, 1).Value = labels(j)
        Next j
    Next i
    
    ' 2c. Apply light blue background to column A
    wsTarget.Range("A2:A" & (blockCount * 14 + 1)).Interior.Color = RGB(220, 230, 255)
    
    ' 3. Add borders around blocks
    For i = 0 To blockCount - 1
        ' Set the block range
        Set blockRange = wsTarget.Range("A" & (2 + i * 14) & ":D" & (15 + i * 14))
        
        ' Apply thick outer border
        With blockRange.Borders(xlEdgeLeft)
            .LineStyle = xlContinuous
            .Weight = xlThick
        End With
        With blockRange.Borders(xlEdgeRight)
            .LineStyle = xlContinuous
            .Weight = xlThick
        End With
        With blockRange.Borders(xlEdgeTop)
            .LineStyle = xlContinuous
            .Weight = xlThick
        End With
        With blockRange.Borders(xlEdgeBottom)
            .LineStyle = xlContinuous
            .Weight = xlThick
        End With
        
        ' Apply thin inner borders
        With blockRange.Borders(xlInsideHorizontal)
            .LineStyle = xlContinuous
            .Weight = xlThin
        End With
        With blockRange.Borders(xlInsideVertical)
            .LineStyle = xlContinuous
            .Weight = xlThin
        End With
    Next i
    
    ' Autofit column A to display all labels properly
    wsTarget.Columns("A:A").AutoFit
    wsTarget.Columns("B:B").AutoFit
    wsTarget.Columns("C:C").AutoFit
    wsTarget.Columns("D:D").AutoFit
    
    ' Save the target workbook
    On Error Resume Next
    wbTarget.SaveAs targetPath & targetFileName, FileFormat:=xlOpenXMLWorkbook
    
    If Err.Number <> 0 Then
        MsgBox "Error saving file to " & targetPath & targetFileName & vbCrLf & _
               "Error: " & Err.Description, vbExclamation, "Save Error"
        
        ' Restore application settings
        Application.ScreenUpdating = True
        Application.Calculation = xlCalculationAutomatic
        Application.EnableEvents = True
        Application.DisplayAlerts = True
        Exit Sub
    Else
        MsgBox "File successfully created at " & targetPath & targetFileName, vbInformation, "Success"
    End If
    On Error GoTo 0
    
    ' Close the target workbook
    wbTarget.Close SaveChanges:=False
    
'    ' Run command line operations
'    Set shellObj = CreateObject("WScript.Shell")
'    waitOnReturn = True  ' Wait for each command to complete before proceeding
'    windowStyle = 1      ' 1 = normal window
'    
'    ' Display status message
'    Application.StatusBar = "Running command line operations. Please wait..."
'    
'    ' First command: Navigate to the script directory
'    
'    ' Second command: Run Python script
'    cmdPath = cmdPath & "python main_sch.py xlsx_initial/newpref.xlsx --time-limit 300 --verbose --time-interval 5 && "
'    
'    ' Third command: Navigate to gear_xls
'    cmdPath = cmdPath & "cd gear_xls && "
'    
'    ' Fourth command: Run the second Python script
'    cmdPath = cmdPath & "python main.py"
'    
'    ' Execute all commands in sequence
'    execStatus = shellObj.Run(cmdPath, windowStyle, waitOnReturn)
'    
'    ' Report status
'    If execStatus = 0 Then
'        MsgBox "All command line operations completed successfully.", vbInformation, "Command Line Success"
'    Else
'        MsgBox "Command line operations completed with exit code: " & execStatus, vbExclamation, "Command Line Execution"
'    End If
    
    ' Clear status bar
    Application.StatusBar = False
    
    ' Restore application settings
    Application.ScreenUpdating = True
    Application.Calculation = xlCalculationAutomatic
    Application.EnableEvents = True
    Application.DisplayAlerts = True
    
    ' Clean up
    Set wsTarget = Nothing
    Set wsMetadata = Nothing
    Set wsSource = Nothing
    Set wbTarget = Nothing
    Set wbSource = Nothing
'    Set shellObj = Nothing
End Sub

Private Function ScheduleColumn(ws As Worksheet, canonicalName As String, oldName As String) As Long
    Dim columnIndex As Long
    Dim header As String
    For columnIndex = 1 To ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column
        header = LCase$(Trim$(CStr(ws.Cells(1, columnIndex).Value)))
        If header = LCase$(canonicalName) Or (oldName <> "" And header = LCase$(oldName)) Then
            ScheduleColumn = columnIndex
            Exit Function
        End If
    Next columnIndex
    ScheduleColumn = 0
End Function

Private Function ScheduleCell(ws As Worksheet, rowIndex As Long, columnIndex As Long) As String
    If columnIndex > 0 Then
        ScheduleCell = CStr(ws.Cells(rowIndex, columnIndex).Value)
    Else
        ScheduleCell = ""
    End If
End Function



