Attribute VB_Name = "PlanningMacros"
' =====================================================================
' PlanningMacros.bas -- VBA macros for the schedule planning sheet
'
' INSTALLATION:
'   1. Open schedule_planning.xlsx
'   2. Press Alt+F11 (VBA Editor)
'   3. Menu: Insert -> Module
'   4. Paste the contents of this file into the new module
'   5. Save the workbook as .xlsm (macro-enabled format)
'
' ASSIGNING TO BUTTONS (recommended):
'   Developer tab -> Insert -> Button -> assign macro
'   Or: Alt+F8 -> select macro -> Run
' =====================================================================
Option Explicit

' ---------------------------------------------------------------------
' Configuration -- adjust if sheet names change
' ---------------------------------------------------------------------
Private Const SECTION_HEIGHT    As Long = 14        ' rows per planning section
Private Const DATA_START_ROW    As Long = 2         ' first data row (row 1 is the header)
Private Const PLANNUNG_SHEET    As String = "Plannung"
Private Const LISTE_SHEET       As String = "Liste"

' Row offsets within a section (0 = first row of the section)
Private Const R_SUBJECT         As Long = 0   ' Subject
Private Const R_GROUP           As Long = 1   ' Group
Private Const R_TEACHER         As Long = 2   ' Teacher
Private Const R_ROOM            As Long = 3   ' Room (main)
Private Const R_ROOM_ALT1       As Long = 4   ' Room alt. 1
Private Const R_ROOM_ALT2       As Long = 5   ' Room alt. 2
Private Const R_ROOM_ALT3       As Long = 6   ' Room alt. 3
Private Const R_BUILDING        As Long = 7   ' Building
Private Const R_DURATION        As Long = 8   ' Duration (min)
Private Const R_DAY             As Long = 9   ' Day
Private Const R_START           As Long = 10  ' Start time
Private Const R_END             As Long = 11  ' End time
Private Const R_PAUSE_BEFORE    As Long = 12  ' Break before (min)
Private Const R_PAUSE_AFTER     As Long = 13  ' Break after (min)

' =====================================================================
' PRIVATE HELPERS
' =====================================================================

' Returns the 1-based section number for a given sheet row.
' Returns 0 if the row is above the data area (i.e. the header row).
Private Function SectionForRow(rowNum As Long) As Long
    If rowNum < DATA_START_ROW Then
        SectionForRow = 0
    Else
        SectionForRow = (rowNum - DATA_START_ROW) \ SECTION_HEIGHT + 1
    End If
End Function

' Returns the first sheet row of section N (1-based).
Private Function SectionStart(sectionNum As Long) As Long
    SectionStart = DATA_START_ROW + (sectionNum - 1) * SECTION_HEIGHT
End Function

' Returns the total number of sections, determined by the last
' occupied row in column A (labels are always present in column A).
Private Function SectionCount(ws As Worksheet) As Long
    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, "A").End(xlUp).Row
    If lastRow < DATA_START_ROW Then
        SectionCount = 0
    Else
        SectionCount = (lastRow - DATA_START_ROW) \ SECTION_HEIGHT + 1
    End If
End Function

' Applies a dropdown list validation to a single cell.
' listeCol: column letter on the Liste sheet (e.g. "G").
' Uses OFFSET+COUNTA so the dropdown expands automatically
' when new values are added to the Liste sheet.
Private Sub ApplyDropdown(cell As Range, listeCol As String)
    Dim formula As String
    formula = "=OFFSET(" & LISTE_SHEET & "!$" & listeCol & "$1,0,0," & _
              "COUNTA(" & LISTE_SHEET & "!$" & listeCol & ":$" & listeCol & "),1)"
    With cell.Validation
        .Delete
        .Add Type:=xlValidateList, _
             AlertStyle:=xlValidAlertInformation, _
             Formula1:=formula
        .IgnoreBlank = True
        .InCellDropdown = True
        .ShowError = False   ' allow free-text entry not in the list
    End With
End Sub

' Applies all dropdown validations for a section starting at startRow.
' Covers columns B (main activity), C and D (linked activities).
Private Sub ApplySectionValidations(ws As Worksheet, startRow As Long)
    Dim col As Variant
    For Each col In Array("B", "C", "D")
        ' Subject -> Liste column G
        ApplyDropdown ws.Cells(startRow + R_SUBJECT,      col), "G"
        ' Group -> Liste column D
        ApplyDropdown ws.Cells(startRow + R_GROUP,        col), "D"
        ' Teacher -> Liste column A
        ApplyDropdown ws.Cells(startRow + R_TEACHER,      col), "A"
        ' Room (main + alternatives) -> Liste column B
        ApplyDropdown ws.Cells(startRow + R_ROOM,         col), "B"
        ApplyDropdown ws.Cells(startRow + R_ROOM_ALT1,    col), "B"
        ApplyDropdown ws.Cells(startRow + R_ROOM_ALT2,    col), "B"
        ApplyDropdown ws.Cells(startRow + R_ROOM_ALT3,    col), "B"
        ' Building -> Liste column C
        ApplyDropdown ws.Cells(startRow + R_BUILDING,     col), "C"
        ' Duration -> Liste column E
        ApplyDropdown ws.Cells(startRow + R_DURATION,     col), "E"
        ' Day -> Liste column H
        ApplyDropdown ws.Cells(startRow + R_DAY,          col), "H"
        ' Break before / after -> Liste column F
        ApplyDropdown ws.Cells(startRow + R_PAUSE_BEFORE, col), "F"
        ApplyDropdown ws.Cells(startRow + R_PAUSE_AFTER,  col), "F"
        ' R_START and R_END (time fields) -- free text, no dropdown
    Next col
End Sub

' Writes row labels into column A for the section starting at startRow.
' Cell values must remain in Russian as required by the planning format.
Private Sub FillLabels(ws As Worksheet, startRow As Long)
    ws.Cells(startRow + R_SUBJECT,      "A").Value = "Дисциплина"
    ws.Cells(startRow + R_GROUP,        "A").Value = "Группа"
    ws.Cells(startRow + R_TEACHER,      "A").Value = "Преподаватель"
    ws.Cells(startRow + R_ROOM,         "A").Value = "Кабинет"
    ws.Cells(startRow + R_ROOM_ALT1,    "A").Value = "Кабинет альтерн. 1"
    ws.Cells(startRow + R_ROOM_ALT2,    "A").Value = "Кабинет альтерн. 2"
    ws.Cells(startRow + R_ROOM_ALT3,    "A").Value = "Кабинет альтерн. 3"
    ws.Cells(startRow + R_BUILDING,     "A").Value = "Здание"
    ws.Cells(startRow + R_DURATION,     "A").Value = "Продолжительность (мин)"
    ws.Cells(startRow + R_DAY,          "A").Value = "День"
    ws.Cells(startRow + R_START,        "A").Value = "Начало"
    ws.Cells(startRow + R_END,          "A").Value = "Конец"
    ws.Cells(startRow + R_PAUSE_BEFORE, "A").Value = "Перерыв до (мин)"
    ws.Cells(startRow + R_PAUSE_AFTER,  "A").Value = "Перерыв после (мин)"
End Sub

' =====================================================================
' MACRO 1: Delete the current planning section
' The section that contains the active cell is deleted.
' Remaining sections below shift up automatically.
' Run: Alt+F8 -> DeleteCurrentSection -> Run
' =====================================================================
Public Sub DeleteCurrentSection()
    ' Verify the user is on the correct sheet
    If ActiveSheet.Name <> PLANNUNG_SHEET Then
        MsgBox "Please switch to sheet '" & PLANNUNG_SHEET & "' and select " & _
               "a cell inside the section you want to delete.", _
               vbExclamation, "Wrong sheet"
        Exit Sub
    End If

    Dim ws As Worksheet
    Set ws = ActiveSheet

    ' Determine the section from the cursor position
    Dim curRow  As Long
    Dim secNum  As Long
    curRow = ActiveCell.Row
    secNum = SectionForRow(curRow)

    If secNum = 0 Then
        MsgBox "The active cell is in the header row." & vbCrLf & _
               "Please select a cell inside a planning section.", _
               vbExclamation, "No section found"
        Exit Sub
    End If

    If secNum > SectionCount(ws) Then
        MsgBox "The active cell is below the last section." & vbCrLf & _
               "Please select a cell inside a planning section.", _
               vbExclamation, "No section found"
        Exit Sub
    End If

    Dim secStart    As Long
    Dim secEnd      As Long
    secStart = SectionStart(secNum)
    secEnd   = secStart + SECTION_HEIGHT - 1

    ' Confirmation dialog showing the exact row range
    Dim rangeLabel  As String
    rangeLabel = PLANNUNG_SHEET & "!" & secStart & ":" & secEnd

    Dim answer As Integer
    answer = MsgBox("Planning section in range " & rangeLabel & " will be deleted." & _
                    vbCrLf & vbCrLf & "Are you sure?", _
                    vbYesNo + vbQuestion, "Confirm deletion")

    If answer <> vbYes Then Exit Sub

    ' Delete the section rows; rows below shift up automatically
    ws.Rows(secStart & ":" & secEnd).Delete Shift:=xlUp

    MsgBox "Section deleted. Remaining sections have shifted up.", _
           vbInformation, "Done"
End Sub

' =====================================================================
' MACRO 2: Add a new planning section
' The new section is appended after the last existing section.
' Formatting (borders, colors) is copied from the last section.
' Run: Alt+F8 -> AddNewSection -> Run
' =====================================================================
Public Sub AddNewSection()
    ' Verify required sheets exist
    Dim ws      As Worksheet
    Dim wsListe As Worksheet

    On Error Resume Next
    Set ws = ThisWorkbook.Sheets(PLANNUNG_SHEET)
    On Error GoTo 0
    If ws Is Nothing Then
        MsgBox "Sheet '" & PLANNUNG_SHEET & "' not found in this workbook.", _
               vbCritical, "Error"
        Exit Sub
    End If

    On Error Resume Next
    Set wsListe = ThisWorkbook.Sheets(LISTE_SHEET)
    On Error GoTo 0
    If wsListe Is Nothing Then
        MsgBox "Sheet '" & LISTE_SHEET & "' not found in this workbook." & vbCrLf & _
               "Dropdown lists cannot be created without it.", _
               vbCritical, "Error"
        Exit Sub
    End If

    Dim total       As Long
    Dim newStart    As Long
    total    = SectionCount(ws)
    newStart = SectionStart(total + 1)  ' first row after all existing sections

    Application.ScreenUpdating = False

    ' Copy formatting from the last existing section (borders, colors, row heights)
    If total > 0 Then
        Dim srcStart As Long
        srcStart = SectionStart(total)

        ws.Rows(srcStart & ":" & (srcStart + SECTION_HEIGHT - 1)).Copy _
            Destination:=ws.Cells(newStart, 1)

        ' Clear data values in columns B-D; keep formatting
        ws.Range( _
            ws.Cells(newStart, "B"), _
            ws.Cells(newStart + SECTION_HEIGHT - 1, "D") _
        ).ClearContents

        Application.CutCopyMode = False
    End If

    ' Write labels into column A (ensures correct text regardless of what was copied)
    FillLabels ws, newStart

    ' Apply dropdown validations to columns B, C, D
    ApplySectionValidations ws, newStart

    Application.ScreenUpdating = True

    ' Move the cursor to the first data cell of the new section
    ws.Activate
    ws.Cells(newStart, "B").Select

    MsgBox "New section added (rows " & newStart & " - " & _
           (newStart + SECTION_HEIGHT - 1) & ").", _
           vbInformation, "Done"
End Sub

' =====================================================================
' MACRO 3: Repair dropdown lists in all existing sections
' Use this if sections were added manually without validation,
' or after the Liste sheet has been updated with new values.
' Run: Alt+F8 -> RepairAllValidations -> Run
' =====================================================================
Public Sub RepairAllValidations()
    Dim ws      As Worksheet
    Dim wsListe As Worksheet

    On Error Resume Next
    Set ws = ThisWorkbook.Sheets(PLANNUNG_SHEET)
    On Error GoTo 0
    If ws Is Nothing Then
        MsgBox "Sheet '" & PLANNUNG_SHEET & "' not found.", vbCritical, "Error"
        Exit Sub
    End If

    On Error Resume Next
    Set wsListe = ThisWorkbook.Sheets(LISTE_SHEET)
    On Error GoTo 0
    If wsListe Is Nothing Then
        MsgBox "Sheet '" & LISTE_SHEET & "' not found.", vbCritical, "Error"
        Exit Sub
    End If

    Dim total As Long
    total = SectionCount(ws)

    If total = 0 Then
        MsgBox "No planning sections found on sheet '" & PLANNUNG_SHEET & "'.", _
               vbInformation, "Nothing to do"
        Exit Sub
    End If

    Dim answer As Integer
    answer = MsgBox("Dropdown lists will be rebuilt in all " & total & _
                    " section(s) on sheet '" & PLANNUNG_SHEET & "'." & _
                    vbCrLf & vbCrLf & "Continue?", _
                    vbYesNo + vbQuestion, "Repair dropdown lists")
    If answer <> vbYes Then Exit Sub

    Application.ScreenUpdating = False

    Dim i As Long
    For i = 1 To total
        ApplySectionValidations ws, SectionStart(i)
    Next i

    Application.ScreenUpdating = True

    MsgBox "Dropdown lists successfully rebuilt in all " & total & " section(s).", _
           vbInformation, "Done"
End Sub
