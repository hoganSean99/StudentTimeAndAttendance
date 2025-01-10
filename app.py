from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import LargeBinary
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta
import csv
import io
import os
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import base64
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from sklearn.linear_model import LinearRegression
import numpy as np

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///StudentMonitoringDB.db'
app.config['SECRET_KEY'] = 'your_secret_key'
db = SQLAlchemy(app)

# Database Models
class Class(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    students = db.relationship('Student', backref='class_', lazy=True)
    exams = db.relationship('Exam', backref='class_', lazy=True)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    exam_results = db.relationship('ExamResult', backref='student', lazy=True)

class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    pdf_data = db.Column(LargeBinary) # NEW

class ExamResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    score = db.Column(db.Float, nullable=False)
    exam = db.relationship('Exam', backref='results')  # Add this relationship

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(1), nullable=False)  # P = Present, A = Absent, L = Late
    
class Homework(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date_assigned = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    comments = db.Column(db.String(255))

    # Define relationship
    student = db.relationship('Student', backref='homework')
    
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)  # Store as Date
    description = db.Column(db.Text)
    color = db.Column(db.String(7), default="#3788d8")
    file_data = db.Column(db.LargeBinary)
    file_name = db.Column(db.String(100))

# Association Table for GrindSession and GrindStudent
grinds_session_students = db.Table(
    'grinds_session_students',
    db.Column('grinds_session_id', db.Integer, db.ForeignKey('grind_session.id'), primary_key=True),
    db.Column('grind_student_id', db.Integer, db.ForeignKey('grind_student.id'), primary_key=True)
)

class GrindSubject(db.Model):
    __tablename__ = 'grind_subject'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

class GrindStudent(db.Model):
    __tablename__ = 'grind_student'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=True)

class GrindSession(db.Model):
    __tablename__ = 'grind_session'
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('grind_subject.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(8), nullable=False)  # Store time as a string (e.g., 'HH:MM:SS')
    price = db.Column(db.Float, nullable=False)
    students = db.relationship(
        'GrindStudent',
        secondary=grinds_session_students,
        back_populates='sessions'
    )

    # Relationships
    subject = db.relationship('GrindSubject', backref=db.backref('sessions', lazy=True))
    students = db.relationship(
        'GrindStudent',
        secondary=grinds_session_students,
        backref=db.backref('sessions', lazy='dynamic')
    )


# Routes
@app.route('/')
def home():
    total_students = Student.query.count()
    total_classes = Class.query.count()

    # Fetch latest exams with class names
    latest_exams = (
        db.session.query(Exam, Class.name.label('class_name'))
        .join(Class, Exam.class_id == Class.id)
        .filter(Exam.date >= datetime.now())  # Show only upcoming exams
        .order_by(Exam.date.asc())
        .all()
    )

    # Fetch recent attendance with student names
    attendance_summary = (
        db.session.query(Attendance, Student.name.label('student_name'))
        .join(Student, Attendance.student_id == Student.id)
        .filter(
            Attendance.status == 'A',  # Filter for absent students only
            Attendance.date >= (datetime.now() - timedelta(days=datetime.now().weekday())),  # Start of this week
            Attendance.date <= datetime.now()  # End of this week (current day)
        )
        .order_by(Attendance.date.desc())
        .all()
    )

    
    return render_template(
        'index.html',
        total_students=total_students,
        total_classes=total_classes,
        latest_exams=latest_exams,
        attendance_summary=attendance_summary
    )




@app.route('/classes')
def classes():
    all_classes = Class.query.all()
    return render_template('classes.html', classes=all_classes)

@app.route('/add_class', methods=['GET', 'POST'])
def add_class():
    if request.method == 'POST':
        class_name = request.form['name']
        new_class = Class(name=class_name)
        db.session.add(new_class)
        db.session.commit()
        flash('Class added successfully!', 'success')
        return redirect(url_for('classes'))
    return render_template('add_class.html')

@app.route('/delete_class/<int:class_id>', methods=['POST'])
def delete_class(class_id):
    # Fetch the class by ID
    class_to_delete = Class.query.get_or_404(class_id)
    
    try:
        # Delete the class
        db.session.delete(class_to_delete)
        db.session.commit()
        flash(f'Class "{class_to_delete.name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting class: {str(e)}', 'danger')

    # Redirect back to the classes page
    return redirect(url_for('view_classes'))

@app.route('/classes')
def view_classes():
    classes = Class.query.all()
    return render_template('classes.html', classes=classes)



@app.route('/students')
def students():
    class_id = request.args.get('class_id')
    all_classes = Class.query.all()
    if class_id:
        all_students = Student.query.filter_by(class_id=class_id).all()
    else:
        all_students = Student.query.all()
    return render_template('students.html', students=all_students, classes=all_classes, selected_class_id=class_id)

@app.route('/export_students')
def export_students():
    class_id = request.args.get('class_id')
    students = Student.query.all() if not class_id else Student.query.filter_by(class_id=class_id).all()

    def generate():
        output = io.StringIO()
        data = csv.writer(output, lineterminator='\n')
        data.writerow(['ID', 'Name', 'Class'])
        for student in students:
            data.writerow([student.id, student.name, student.class_.name])  # Fixed reference to class_
        output.seek(0)
        return output.getvalue()

    return Response(generate(), mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=students.csv"})

@app.route('/add_student', methods=['GET', 'POST'])
def add_student():
    if request.method == 'POST':
        student_name = request.form['name']
        class_id = request.form['class_id']
        new_student = Student(name=student_name, class_id=class_id)
        db.session.add(new_student)
        db.session.commit()
        flash('Student added successfully!', 'success')
        return redirect(url_for('add_student'))
    classes = Class.query.all()
    return render_template('add_student.html', classes=classes)

@app.route('/delete_student/<int:student_id>', methods=['POST'])
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    db.session.delete(student)
    db.session.commit()
    flash('Student deleted successfully!', 'success')
    return redirect(url_for('students'))


@app.route('/attendance', methods=['GET', 'POST'])
def attendance():
    classes = Class.query.all()
    class_id = request.form.get('class_id') or request.args.get('class_id')
    
    # Fetch selected date or default to today
    attendance_date = request.form.get('attendance_date') or request.args.get('attendance_date') or datetime.now().strftime('%Y-%m-%d')
    
    students = []
    attendance_map = {}

    if class_id:
        class_id = int(class_id)
        students = Student.query.filter_by(class_id=class_id).all()
        
        # Convert the attendance_date to a Python date object
        attendance_date_obj = datetime.strptime(attendance_date, '%Y-%m-%d').date()

        # Fetch distinct attendance records for the selected date
        attendance_records = db.session.query(
            Attendance.student_id,
            Attendance.status
        ).filter(
            Attendance.date == attendance_date_obj,
            Attendance.student_id.in_([s.id for s in students])
        ).distinct().all()

        attendance_map = {record.student_id: record.status for record in attendance_records}

    return render_template(
        'attendance.html',
        classes=classes,
        students=students,
        class_id=class_id,
        attendance_records=attendance_map,
        selected_date=attendance_date
    )



@app.route('/attendance_calendar')
def attendance_calendar():
    selected_date = request.args.get('date')
    if selected_date:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        attendance_records = db.session.query(Attendance, Student).join(Student).filter(Attendance.date == selected_date).all()
        return render_template('attendance_list.html', attendance_records=attendance_records, selected_date=selected_date)
    return render_template('calendar_page.html')



@app.route('/get_attendance_events')
def get_attendance_events():
    # Define a list of colors to cycle through for different classes
    colors = ['#1870ff', '#a418ff', '#ff8518', '#F39C12', '#ff1818', '#e1008c']
    color_mapping = {}
    color_index = 0

    records = (
        db.session.query(Attendance.date, Class.name.label('class_name'), Class.id.label('class_id'))
        .join(Student, Attendance.student_id == Student.id)
        .join(Class, Student.class_id == Class.id)
        .order_by(Attendance.date.asc())
        .all()
    )

    # Group by class and assign colors
    unique_events = {}
    for record in records:
        key = (record.date, record.class_name)

        if key not in unique_events:
            # Assign color if not already mapped
            if record.class_name not in color_mapping:
                color_mapping[record.class_name] = colors[color_index % len(colors)]
                color_index += 1

            unique_events[key] = {
                "title": record.class_name,
                "start": record.date.strftime('%Y-%m-%d'),
                "url": url_for('attendance_details', class_id=record.class_id, date=record.date.strftime('%Y-%m-%d')),
                "color": color_mapping[record.class_name]
            }

    return jsonify(list(unique_events.values()))



@app.route('/attendance_details/<int:class_id>/<date>')
def attendance_details(class_id, date):
    date_object = datetime.strptime(date, '%Y-%m-%d').date()
    attendance_records = (
        db.session.query(Attendance, Student, Class.name.label('class_name'))
        .join(Student, Attendance.student_id == Student.id)
        .join(Class, Student.class_id == Class.id)
        .filter(Student.class_id == class_id, Attendance.date == date_object)
        .all()
    )
    class_name = Class.query.get(class_id).name
    return render_template('attendance_details.html', 
                           class_name=class_name, 
                           attendance_records=attendance_records, 
                           date=date)


from datetime import datetime

@app.route('/save_attendance', methods=['POST'])
def save_attendance():
    class_id = request.form.get('class_id')
    attendance_date = request.form.get('attendance_date')

    # Convert the string date to a Python date object
    if isinstance(attendance_date, str):
        attendance_date = datetime.strptime(attendance_date, '%Y-%m-%d').date()

    students = Student.query.filter_by(class_id=class_id).all()

    for student in students:
        status = request.form.get(str(student.id), 'P')  # Default to Present if no value is selected
        existing_record = Attendance.query.filter_by(student_id=student.id, date=attendance_date).first()
        
        if existing_record:
            existing_record.status = status
        else:
            new_attendance = Attendance(
                student_id=student.id,
                date=attendance_date,
                status=status
            )
            db.session.add(new_attendance)

    db.session.commit()
    flash('Attendance saved successfully!', 'success')
    return redirect(url_for('attendance'))


@app.route('/student/<int:student_id>')
def student_details(student_id):
    student = Student.query.get_or_404(student_id)
    
    # Generate Exam Performance Plot
    exam_results = (
        db.session.query(ExamResult)
        .join(Exam)
        .filter(ExamResult.student_id == student_id)
        .order_by(Exam.date)
        .all()
    )
    recorded_exam_ids = [result.exam_id for result in exam_results]
    available_exams = Exam.query.filter_by(class_id=student.class_id).filter(~Exam.id.in_(recorded_exam_ids)).all()

    scores = [result.score for result in exam_results]
    dates = [result.exam.date for result in exam_results]
    titles = [result.exam.title for result in exam_results]

    plt.figure(figsize=(9, 4), dpi=150)
    plt.plot(dates, scores, marker='o', linestyle='-', color='#1f77b4', linewidth=1.5)
    plt.fill_between(dates, scores, color='#B3E5FC')

    for i, title in enumerate(titles):
        plt.annotate(
            title,
            (dates[i], scores[i]),
            textcoords="offset points",
            xytext=(5, 5),
            ha='center',
            fontsize=9
        )

    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%b %d, %Y'))
    plt.xticks(rotation=30, fontsize=10)
    plt.yticks(fontsize=10)
    plt.title(f'Exam Performance for {student.name}', fontsize=14)
    plt.xlabel('Exam Date', fontsize=12)
    plt.ylabel('Score (%)', fontsize=12)
    plt.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7)
    plt.tight_layout(pad=3)

    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', transparent=True)
    buf.seek(0)
    plot_url = base64.b64encode(buf.getvalue()).decode('utf8')
    buf.close()

    # Generate Attendance Pie Chart
    attendance_records = Attendance.query.filter_by(student_id=student_id).all()
    present = sum(1 for record in attendance_records if record.status == 'P')
    absent = sum(1 for record in attendance_records if record.status == 'A')
    late = sum(1 for record in attendance_records if record.status == 'L')
    
    if present == 0 and absent == 0 and late == 0:
    # No attendance data
        chart_url = None
        flash("No attendance data available for this student.", "info")
    else:

        labels = ['Present', 'Absent', 'Late']
        sizes = [present, absent, late]
        colors = ['#2ecc71', '#e74c3c', '#f1c40f']

        plt.figure(figsize=(9, 3))
        patches, texts, autotexts = plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors)
        plt.legend(patches, labels, loc="upper right")
        plt.axis('equal')

        buf = BytesIO()
        plt.savefig(buf, format='png', transparent=True)
        buf.seek(0)
        chart_url = base64.b64encode(buf.getvalue()).decode('utf8')
        plt.close()

    homework_records = Homework.query.filter_by(student_id=student_id).order_by(Homework.date_assigned.desc()).all()

    return render_template(
        'student_detail.html',
        student=student,
        exam_results=exam_results,
        available_exams=available_exams,
        homework_records=homework_records,
        plot_url=plot_url,
        chart_url=chart_url
    )


import os
from flask import request, flash, redirect, url_for
from datetime import datetime
from werkzeug.utils import secure_filename

@app.route('/exams', methods=['GET', 'POST'])
def exams():
    all_classes = Class.query.all()
    
    if request.method == 'POST':
        exam_title = request.form['title']
        class_id = request.form['class_id']
        exam_date = datetime.strptime(request.form['date'], '%Y-%m-%d')

        # Handle PDF file upload
        pdf_file = request.files.get('pdf')
        pdf_data = None
        
        if pdf_file and pdf_file.filename.endswith('.pdf'):
            # Read the PDF file as binary data and store it
            pdf_data = pdf_file.read()

        # Create a new exam object with the exam details and the PDF data
        new_exam = Exam(
            title=exam_title, 
            class_id=class_id, 
            date=exam_date, 
            pdf_data=pdf_data  # Storing the binary data in the database
        )
        
        db.session.add(new_exam)
        db.session.commit()
        flash('Exam added successfully!', 'success')
        return redirect(url_for('exams'))
    
    all_exams = (
        db.session.query(Exam, Class.name.label('class_name'))
        .join(Class, Exam.class_id == Class.id)
        .order_by(Exam.date.desc())
        .all()
    )
    
    return render_template('exams.html', exams=all_exams, classes=all_classes, now=datetime.now().date())

@app.route('/exam/<int:exam_id>/edit', methods=['GET', 'POST'])
def edit_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    all_classes = Class.query.all()

    if request.method == 'POST':
        # Update the exam details from the form
        exam.title = request.form['title']
        exam.class_id = request.form['class_id']
        exam.date = datetime.strptime(request.form['date'], '%Y-%m-%d')

        # Handle PDF upload if a new one is provided
        pdf_file = request.files.get('pdf')
        if pdf_file and pdf_file.filename.endswith('.pdf'):
            exam.pdf_data = pdf_file.read()  # Replace the existing PDF

        db.session.commit()
        flash('Exam updated successfully!', 'success')
        return redirect(url_for('exams'))

    return render_template('edit_exam.html', exam=exam, classes=all_classes)

@app.route('/exam/<int:exam_id>/download')
def download_pdf(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    
    # Check if the exam has PDF data
    if exam.pdf_data:
        return Response(
            exam.pdf_data,  # Binary PDF data
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename={exam.title}.pdf'}
        )
    
    flash('No PDF available for this exam.', 'danger')
    return redirect(url_for('exams'))

@app.route('/exam/<int:exam_id>/delete', methods=['POST'])
def delete_exam(exam_id):
    # Get the exam to be deleted
    exam = Exam.query.get_or_404(exam_id)

    # Delete the exam from the database
    db.session.delete(exam)
    db.session.commit()
    
    flash('Exam deleted successfully!', 'danger')
    return redirect(url_for('exams'))

@app.route('/record_exam/<int:student_id>', methods=['POST'])
def record_exam(student_id):
    exam_id = request.form['exam_id']
    score = request.form['score']
    existing_result = ExamResult.query.filter_by(student_id=student_id, exam_id=exam_id).first()
    if existing_result:
        existing_result.score = score
        flash('Exam score updated!', 'success')
    else:
        new_result = ExamResult(exam_id=exam_id, student_id=student_id, score=score)
        db.session.add(new_result)
        flash('Exam score recorded!', 'success')
    db.session.commit()
    return redirect(url_for('student_details', student_id=student_id))

@app.route('/student/<int:student_id>/export_pdf')
def export_student_pdf(student_id):
    student = Student.query.get_or_404(student_id)
    exam_results = ExamResult.query.filter_by(student_id=student_id).all()

    # Create PDF Canvas
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(f"Student_Report_{student.name}.pdf")

    # Title Section
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawCentredString(300, 770, f"{student.name}'s Performance Report")
    
    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(300, 740, f"Class: {student.class_.name}")
    pdf.line(50, 730, 550, 730)

    # Exam Results Section
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, 700, "Exam Results")
    pdf.setFont("Helvetica", 12)

    y = 680
    row_height = 20

    pdf.setFillColorRGB(0.9, 0.9, 0.9)
    pdf.rect(50, y - 10, 500, row_height, fill=1)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.drawString(60, y, "Exam Title")
    pdf.drawString(250, y, "Date")
    pdf.drawString(400, y, "Score (%)")
    
    y -= row_height + 5
    for result in exam_results:
        pdf.drawString(60, y, result.exam.title)
        pdf.drawString(250, y, result.exam.date.strftime('%Y-%m-%d'))
        pdf.drawString(400, y, f"{result.score}%")
        y -= row_height

        # Page Break
        if y < 150:
            pdf.showPage()
            y = 750
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawString(50, 700, "Exam Results (Continued)")

    # Generate Performance Graph
    scores = [result.score for result in exam_results]
    dates = [result.exam.date for result in exam_results]

    plt.figure(figsize=(10, 5), dpi=200)
    plt.plot(dates, scores, marker='o', linestyle='-', color='#1f77b4', linewidth=2)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%b %d, %Y'))
    plt.xticks(rotation=45, fontsize=10)
    plt.title(f'Performance Over Time for {student.name}', fontsize=16)
    plt.xlabel('Exam Date', fontsize=14)
    plt.ylabel('Score (%)', fontsize=14)
    plt.grid(True, which='both', linestyle='--', linewidth=0.7)
    plt.tight_layout()

    # Save Graph to Buffer
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    
    # Add Graph to PDF
    pdf.showPage()
    pdf.drawImage(ImageReader(buf), 75, 250, width=450, height=300)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(300, 580, "Performance Graph")

    # Generate Attendance Pie Chart
    attendance_records = Attendance.query.filter_by(student_id=student_id).all()
    present = sum(1 for record in attendance_records if record.status == 'P')
    absent = sum(1 for record in attendance_records if record.status == 'A')
    late = sum(1 for record in attendance_records if record.status == 'L')

    labels = ['Present', 'Absent', 'Late']
    sizes = [present, absent, late]
    colors = ['#2ecc71', '#e74c3c', '#f1c40f']

    plt.figure(figsize=(7, 4))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors)
    plt.axis('equal')
    plt.tight_layout()

    buf_pie = BytesIO()
    plt.savefig(buf_pie, format='png', transparent=True)
    buf_pie.seek(0)

    # Add Pie Chart to PDF
    pdf.showPage()
    pdf.drawImage(ImageReader(buf_pie), 125, 300, width=350, height=250)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(300, 580, "Attendance Overview")

    # Finalize PDF
    pdf.save()
    buffer.seek(0)

    return Response(buffer, mimetype='application/pdf',
                    headers={"Content-Disposition": f"attachment;filename=Student_Report_{student.name}.pdf"})

    
from datetime import datetime

@app.route('/homework', methods=['GET', 'POST'])
def homework():
    class_id = request.args.get('class_id')
    selected_date = request.args.get('homework_date') or datetime.now().date().strftime('%Y-%m-%d')
    all_classes = Class.query.all()
    students = []
    homework_done = {}
    homework_comments = {}

    if class_id:
        # Fetch students and homework records
        students = Student.query.filter_by(class_id=class_id).all()
        completed_homework = Homework.query.filter(
            Homework.student_id.in_([student.id for student in students]),
            Homework.date_assigned == datetime.strptime(selected_date, '%Y-%m-%d').date()
        ).all()

        # Map completed homework and comments
        homework_done = {hw.student_id: hw.completed for hw in completed_homework}
        homework_comments = {hw.student_id: hw.comments for hw in completed_homework}

    if request.method == 'POST':
        for student in students:
            completed = request.form.get(f'completed_{student.id}') == 'on'
            comment = request.form.get(f'comment_{student.id}', '')

            # Check if homework exists
            existing_homework = Homework.query.filter_by(
                student_id=student.id,
                date_assigned=datetime.strptime(selected_date, '%Y-%m-%d').date()
            ).first()

            if existing_homework:
                # Update existing record
                existing_homework.completed = completed
                existing_homework.comments = comment
            else:
                # Add new record
                new_homework = Homework(
                    student_id=student.id,
                    date_assigned=datetime.strptime(selected_date, '%Y-%m-%d').date(),
                    completed=completed,
                    comments=comment
                )
                db.session.add(new_homework)

        db.session.commit()
        flash('Homework records updated successfully!', 'success')
        return redirect(url_for('homework', class_id=class_id, homework_date=selected_date))

    return render_template(
        'homework.html',
        students=students,
        classes=all_classes,
        selected_class_id=class_id,
        selected_date=selected_date,
        homework_done=homework_done,
        homework_comments=homework_comments
    )

@app.route('/homework_details/<int:class_id>/<date>')
def homework_details(class_id, date):
    date_object = datetime.strptime(date, '%Y-%m-%d').date()
    class_name = Class.query.get_or_404(class_id).name
    
    # Fetch homework records and student information
    homework_records = (
        db.session.query(Homework, Student)
        .join(Student, Homework.student_id == Student.id)
        .filter(Student.class_id == class_id, Homework.date_assigned == date_object)
        .all()
    )
    
    return render_template(
        'homework_details.html',
        class_name=class_name,
        date=date_object.strftime('%Y-%m-%d'),
        homework_records=homework_records
    )
    

@app.route('/calendar')
def calendar():
    events = Event.query.all()
    exams = Exam.query.all()

    calendar_events = [
        {
            'title': event.title,
            'start': event.date.strftime('%Y-%m-%d'),
            'allDay': True,
            'id': event.id
        } for event in events
    ]

    calendar_events += [
        {
            'title': f"Exam: {exam.title}",
            'start': exam.date.strftime('%Y-%m-%d'),
            'allDay': True
        } for exam in exams
    ]

    return render_template('calendar.html', events=calendar_events)

@app.route('/get_events')
def get_events():
    events = Event.query.all()
    exams = Exam.query.all()
    
    # Attendance records
    attendance_records = (
        db.session.query(Attendance.date, Class.name, Class.id)
        .join(Student, Attendance.student_id == Student.id)
        .join(Class, Student.class_id == Class.id)
        .with_entities(Attendance.date, Class.name, Class.id)
        .distinct(Attendance.date, Student.class_id)
        .all()
    )
    
    # Homework records
    homework_records = (
        db.session.query(Homework.date_assigned, Class.name, Class.id)
        .join(Student, Homework.student_id == Student.id)
        .join(Class, Student.class_id == Class.id)
        .with_entities(Homework.date_assigned, Class.name, Class.id)
        .distinct(Homework.date_assigned, Student.class_id)
        .all()
    )
    
    # Event data
    events_data = [{
        'id': event.id,
        'title': event.title,
        'start': event.date.strftime('%Y-%m-%d'),
        'color': '#9b59b6',
        'type': 'event',
        'description': event.description
    } for event in events]

    exams_data = [{
        'id': exam.id,
        'title': f'E - {exam.title}',
        'start': exam.date.strftime('%Y-%m-%d'),
        'color': '#ff6347',
        'type': 'exam',
    } for exam in exams]

    attendance_data = [{
        'id': f"{record_date.strftime('%Y%m%d')}_{class_id}",
        'title': f'A - {class_name}',
        'start': record_date.strftime('%Y-%m-%d'),
        'color': '#2ecc71',
        'type': 'attendance',
        'class_id': class_id,
    } for record_date, class_name, class_id in attendance_records]

    homework_data = [{
        'id': f"{record_date.strftime('%Y%m%d')}_{class_id}",
        'title': f'H - {class_name}',
        'start': record_date.strftime('%Y-%m-%d'),
        'color': '#3498db',
        'type': 'homework',
        'class_id': class_id,
    } for record_date, class_name, class_id in homework_records]

    all_events = events_data + exams_data + attendance_data + homework_data

    return jsonify(all_events)


@app.route('/attendance_details_date/<int:class_id>/<date>')
def attendance_details_date(class_id, date):
    date_object = datetime.strptime(date, '%Y-%m-%d').date()
    attendance_records = (
        db.session.query(Attendance, Student.name.label('student_name'))
        .join(Student, Attendance.student_id == Student.id)
        .filter(Student.class_id == class_id, Attendance.date == date_object)
        .all()
    )

    class_name = Class.query.get(class_id).name
    return jsonify({
        'title': f'Attendance for {class_name}',
        'date': date_object.strftime('%d-%m-%Y'),
        'attendance': [{
            'student_name': student_name,
            'status': record.status
        } for record, student_name in attendance_records]
    })


@app.route('/exam/<int:exam_id>')
def get_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    class_name = exam.class_.name  # Access the class name through the relationship

    return jsonify({
        'id': exam.id,
        'title': f'Exam - {exam.title}',
        'date': exam.date.strftime('%Y-%m-%d'),
        'description': f'{exam.title} scheduled for {class_name}.',
        'download_url': url_for('download_exam_file', exam_id=exam.id) if exam.pdf_data else None
    })
    
@app.route('/exam/download/<int:exam_id>')
def download_exam_file(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if exam.file_data:
        return send_file(BytesIO(exam.file_data), as_attachment=True, download_name=exam.file_name)

@app.route('/event/<int:event_id>')
def get_event(event_id):
    event = Event.query.get_or_404(event_id)
    return jsonify({
        'id': event.id,
        'title': event.title,
        'date': event.date.strftime('%Y-%m-%d'),
        'description': event.description,
        'file_name': event.file_name,
        'download_url': url_for('download_file', event_id=event.id) if event.file_name else None
    })

@app.route('/download/<int:event_id>')
def download_file(event_id):
    event = Event.query.get_or_404(event_id)
    
    if not event.file_data:
        flash('No file attached to this event.', 'warning')
        return redirect(url_for('calendar'))

    return send_file(
        BytesIO(event.file_data),
        as_attachment=True,
        download_name=event.file_name
    )

@app.route('/add_event', methods=['POST'])
def add_event():
    title = request.form['title']
    date = request.form['date']
    description = request.form['description']
    color = request.form['color']  # Get color from form
    file = request.files.get('file')

    date_object = datetime.strptime(date, '%Y-%m-%d').date()

    new_event = Event(
        title=title,
        date=date_object,
        description=description,
        color=color  # Assign color to the event
    )

    if file:
        new_event.file_data = file.read()
        new_event.file_name = file.filename

    db.session.add(new_event)
    db.session.commit()
    flash('Event added successfully!', 'success')
    return redirect(url_for('calendar'))

@app.route('/predict_results')
def predict_results():
    students = Student.query.all()
    predictions = []

    for student in students:
        # Fetch exam results for the student
        exam_results = (
            db.session.query(ExamResult)
            .join(Exam)
            .filter(ExamResult.student_id == student.id)
            .order_by(Exam.date)
            .all()
        )

        # Get the next upcoming exam
        next_exam = (
            db.session.query(Exam)
            .filter(Exam.class_id == student.class_id)
            .filter(Exam.date > datetime.now())
            .order_by(Exam.date)
            .first()
        )

        # Perform prediction if there are results and an upcoming exam
        if exam_results and next_exam:
            scores = np.array([result.score for result in exam_results]).reshape(-1, 1)
            dates = np.array([i for i in range(len(exam_results))]).reshape(-1, 1)
            
            model = LinearRegression()
            model.fit(dates, scores)
            
            next_result = model.predict(np.array([[len(exam_results)]]))
            predictions.append({
                'student_name': student.name,
                'exam_title': next_exam.title,
                'predicted_score': round(next_result[0][0], 2),
                'exam_date': next_exam.date.strftime('%Y-%m-%d')
            })

    return render_template('predictions.html', predictions=predictions)

@app.route('/grind_subjects')
def grind_subjects():
    subjects = GrindSubject.query.all()
    return render_template('grind_subjects.html', subjects=subjects)

@app.route('/add_grind_subject', methods=['POST'])
def add_grind_subject():
    name = request.form.get('name')
    if name:
        new_subject = GrindSubject(name=name)
        db.session.add(new_subject)
        db.session.commit()
        flash('Grind subject added successfully!', 'success')
    return redirect(url_for('grind_subjects'))

# Grind Students
@app.route('/grind_students')
def grind_students():
    students = GrindStudent.query.all()
    return render_template('grind_students.html', students=students)

@app.route('/add_grind_student', methods=['POST'])
def add_grind_student():
    name = request.form.get('name')
    email = request.form.get('email')
    if name:
        new_student = GrindStudent(name=name, email=email)
        db.session.add(new_student)
        db.session.commit()
        flash('Grind student added successfully!', 'success')
    return redirect(url_for('grind_students'))


@app.route('/add_grinds_session', methods=['POST'])
def add_grinds_session():
    subject_id = request.form.get('subject_id')
    session_date = request.form.get('session_date')
    session_time = request.form.get('time')  # Expecting time as a string (e.g., 'HH:MM')
    price = request.form.get('price')
    student_names = request.form.get('students', '').splitlines()

    if subject_id and session_date and session_time and price:
        # Create a new GrindSession object
        new_session = GrindSession(
            subject_id=int(subject_id),
            date=datetime.strptime(session_date, '%Y-%m-%d').date(),
            time=session_time,  # Directly store the time as a string
            price=float(price)
        )
        db.session.add(new_session)

        # Process each student name
        for student_name in student_names:
            student_name = student_name.strip()
            if student_name:  # Ignore blank lines
                # Check if the student already exists
                student = GrindStudent.query.filter_by(name=student_name).first()
                if not student:
                    student = GrindStudent(name=student_name)
                    db.session.add(student)
                # Link the student to the grind session
                new_session.students.append(student)

        # Commit the session to the database
        db.session.commit()
        flash('Grind session added successfully!', 'success')
    else:
        flash('All fields are required!', 'danger')

    return redirect(url_for('grind_sessions'))





@app.route('/filter_grind_sessions')
def filter_grind_sessions():
    subject_id = request.args.get('subject_id')
    if subject_id:
        sessions = GrindSession.query.filter_by(subject_id=subject_id).join(GrindSubject).join(GrindStudent).add_columns(
            GrindSubject.name.label('subject_name'),
            GrindStudent.name.label('student_name'),
            GrindSession.date,
            GrindSession.time,
            GrindSession.price
        ).all()
        sessions_data = [
            {
                'subject_name': session.subject_name,
                'student_name': session.student_name,
                'date': session.date.strftime('%Y-%m-%d'),
                'time': session.time,
                'price': f"${session.price:.2f}"
            } for session in sessions
        ]
        return jsonify({'sessions': sessions_data})

    return jsonify({'sessions': []})



@app.route('/grind_sessions', methods=['GET', 'POST'])
def grind_sessions():
    # Fetch all grind subjects and grind sessions
    subjects = GrindSubject.query.all()
    sessions = GrindSession.query.options(
        joinedload(GrindSession.subject),
        joinedload(GrindSession.students)
    ).all()

    # Debugging: Verify the subjects and sessions
    if not subjects:
        print("No subjects found")
    else:
        print(f"Subjects: {[subject.name for subject in subjects]}")  # Debug: Subject names
    
    if not sessions:
        print("No sessions found")
    else:
        print(f"Sessions: {[session.subject.name for session in sessions]}")  # Debug: Session subjects

    return render_template(
        'grind_sessions.html',
        subjects=subjects,
        sessions=sessions
    )



        

@app.route('/edit_grinds_session', methods=['POST'])
def edit_grinds_session():
    session_id = request.form.get('session_id')
    subject_id = request.form.get('subject_id')
    session_date = request.form.get('session_date')
    session_time = request.form.get('session_time')
    price = request.form.get('price')
    students = request.form.get('students', '').splitlines()

    session = GrindSession.query.get(session_id)

    if session:
        session.subject_id = subject_id
        session.date = datetime.strptime(session_date, '%Y-%m-%d').date()
        session.time = session_time
        session.price = float(price)
        
        # Update students
        session.students = []  # Clear current students
        for student_name in students:
            student_name = student_name.strip()
            if student_name:
                student = GrindStudent.query.filter_by(name=student_name).first()
                if not student:
                    student = GrindStudent(name=student_name)
                    db.session.add(student)
                session.students.append(student)

        db.session.commit()
        flash('Grind session updated successfully!', 'success')
    else:
        flash('Grind session not found!', 'danger')

    return redirect(url_for('grind_sessions'))


@app.route('/delete_grinds_session/<int:session_id>', methods=['POST'])
def delete_grinds_session(session_id):
    session = GrindSession.query.get_or_404(session_id)
    db.session.delete(session)
    db.session.commit()
    flash('Grinds session deleted successfully!', 'success')
    return redirect(url_for('grind_sessions'))





if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not os.path.exists('attendance.db'):
            db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
