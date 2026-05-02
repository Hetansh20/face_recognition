import pandas as pd, os

xl = pd.ExcelFile('d:/ML/deepface/face_recognition/Student details for AI project.xlsx')
print('Sheets:', xl.sheet_names)
for s in xl.sheet_names:
    df = xl.parse(s)
    df.columns = [str(c).strip() for c in df.columns]
    print(f'\n--- Sheet: {s} ({len(df)} rows) ---')
    print('Columns:', df.columns.tolist())
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].astype(str).str.strip()
    print(df.head(3).to_string())
    if 'Semester' in df.columns or 'Semester ' in df.columns:
        scol = 'Semester ' if 'Semester ' in df.columns else 'Semester'
        print('Semesters:', df[scol].unique())
    if 'Class' in df.columns:
        print('Classes:', df['Class'].unique())
    if 'Lab Batch' in df.columns:
        print('Batches:', df['Lab Batch'].unique())

# Check registered_faces directory
rf_dir = 'd:/ML/deepface/face_recognition/registered_faces'
files = os.listdir(rf_dir)
print(f'\nregistered_faces: {len(files)} files')
print('Sample filenames:', files[:15])
