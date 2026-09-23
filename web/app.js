const fileInput = document.getElementById("fileInput");
const fileName = document.getElementById("fileName");
const analyzeButton = document.getElementById("analyzeButton");
const importButton = document.getElementById("importButton");
const result = document.getElementById("result");
const resultContent = document.getElementById("resultContent");
const resultsButton = document.getElementById("resultsButton");
const dashboard = document.getElementById("dashboard");
const institutionName = document.getElementById("institutionName");
const academicPeriod = document.getElementById("academicPeriod");

const totalStudents = document.getElementById("totalStudents");
const passedStudents = document.getElementById("passedStudents");
const failedStudents = document.getElementById("failedStudents");
const averageScore = document.getElementById("averageScore");

const studentCountLabel = document.getElementById("studentCountLabel");
const studentTableBody = document.getElementById("studentTableBody");

let selectedFile = null;
let previewValid = false;

fileInput.addEventListener("change", () => {
    selectedFile = fileInput.files[0] || null;
    previewValid = false;

    if (!selectedFile) {
        fileName.textContent = "";
        analyzeButton.disabled = true;
        importButton.disabled = true;
        return;
    }

    fileName.textContent = `Selected: ${selectedFile.name}`;
    analyzeButton.disabled = false;
    importButton.disabled = true;
});

analyzeButton.addEventListener("click", async () => {
    if (!selectedFile) return;

    analyzeButton.disabled = true;
    analyzeButton.textContent = "Analyzing...";

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
        const response = await fetch(
            "http://127.0.0.1:8000/api/academic/import/preview",
            {
                method: "POST",
                body: formData
            }
        );

        const data = await response.json();

        result.classList.remove("hidden");

        if (!response.ok) {
            throw new Error(data.detail || "Preview failed.");
        }

        if (data.valid) {
            previewValid = true;
            importButton.disabled = false;

            resultContent.innerHTML = `
                <div class="success">
                    ✓ Workbook validated successfully
                </div>

                <div class="stat">
                    <span>Students to create</span>
                    <strong>${data.students_to_create}</strong>
                </div>

                <div class="stat">
                    <span>Enrollments</span>
                    <strong>${data.enrollments}</strong>
                </div>

                <div class="stat">
                    <span>Marks detected</span>
                    <strong>${data.marks}</strong>
                </div>

                <p style="margin-top:20px;color:#999;">
                    The workbook is ready to import.
                </p>
            `;
        } else {
            previewValid = false;
            importButton.disabled = true;

            resultContent.innerHTML = `
                <div class="error">
                    ✕ Validation failed
                </div>

                <p style="margin-top:15px;">
                    ${data.errors.map(error =>
                        `${error.sheet}: ${error.message}`
                    ).join("<br>")}
                </p>
            `;
        }

    } catch (error) {
        previewValid = false;
        importButton.disabled = true;

        result.classList.remove("hidden");

        resultContent.innerHTML = `
            <div class="error">
                Could not connect to the Academic API.
            </div>

            <p style="margin-top:15px;color:#999;">
                ${error.message}
            </p>
        `;
    }

    analyzeButton.disabled = false;
    analyzeButton.textContent = "Preview Workbook";
});

importButton.addEventListener("click", async () => {
    if (!selectedFile || !previewValid) return;

    importButton.disabled = true;
    analyzeButton.disabled = true;
    importButton.textContent = "Importing...";

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
        const response = await fetch(
            "http://127.0.0.1:8000/api/academic/import",
            {
                method: "POST",
                body: formData
            }
        );

        const data = await response.json();

        result.classList.remove("hidden");

        if (!response.ok) {
            throw new Error(
                data.detail?.message ||
                data.detail ||
                "Import failed."
            );
        }

        resultContent.innerHTML = `
            <div class="success">
                ✓ Data imported successfully
            </div>

            <div class="stat">
                <span>Students created</span>
                <strong>${data.students_created}</strong>
            </div>

            <div class="stat">
                <span>Enrollments created</span>
                <strong>${data.enrollments_created}</strong>
            </div>

            <div class="stat">
                <span>Marks imported</span>
                <strong>${data.marks_imported}</strong>
            </div>

            <p style="margin-top:20px;color:#999;">
                Your academic data is now stored in QUADxy.
            </p>
        `;

    } catch (error) {
        resultContent.innerHTML = `
            <div class="error">
                ✕ Import failed
            </div>

            <p style="margin-top:15px;color:#999;">
                ${error.message}
            </p>
        `;
    }

    importButton.disabled = false;
    analyzeButton.disabled = false;
    importButton.textContent = "Import Data";
});
resultsButton.addEventListener("click", async () => {

    resultsButton.disabled = true;
    resultsButton.textContent = "Loading...";

    try {

        const response = await fetch(
            "http://127.0.0.1:8000/api/academic/results"
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.detail || "Could not load academic results."
            );
        }

        const students = data.results || [];

        /*
         * =========================
         * CALCULATE DASHBOARD STATS
         * =========================
         */

        const total = students.length;

        const passed = students.filter(
            student => student.passed
        ).length;

        const failed = total - passed;

        const average = total > 0
            ? students.reduce(
                (sum, student) =>
                    sum + student.overall_percentage,
                0
            ) / total
            : 0;


        /*
         * =========================
         * INSTITUTION INFORMATION
         * =========================
         */

        institutionName.textContent =
            data.institution || "Academic Institution";


        if (students.length > 0) {

            academicPeriod.textContent =
                `${students[0].year_name} • ${students[0].term_name}`;

        } else {

            academicPeriod.textContent =
                "No academic results available";

        }


        /*
         * =========================
         * SUMMARY CARDS
         * =========================
         */

        totalStudents.textContent = total;

        passedStudents.textContent = passed;

        failedStudents.textContent = failed;

        averageScore.textContent =
            `${average.toFixed(1)}%`;

        studentCountLabel.textContent =
            `${total} student${total === 1 ? "" : "s"}`;


        /*
         * =========================
         * STUDENT TABLE
         * =========================
         */

        studentTableBody.innerHTML = students.map((student, index) => {
    const statusClass = student.passed
        ? "status-passed"
        : "status-failed";

    const statusText = student.passed
        ? "Passed"
        : "Failed";

    return `
        <tr class="student-row" data-student-index="${index}">
            <td class="roll-cell">${student.roll_no}</td>

            <td class="student-name-cell">
                ${student.student_name}
            </td>

            <td class="score-cell">
                ${student.overall_percentage.toFixed(1)}%
            </td>

            <td class="grade-cell">
                ${student.grade}
            </td>

            <td>
                <span class="status-badge ${statusClass}">
                    ${statusText}
                </span>
            </td>
        </tr>
    `;
}).join("");


const studentRows =
    document.querySelectorAll(".student-row");

studentRows.forEach((row) => {

    row.addEventListener("click", () => {

        const studentIndex =
            Number(row.dataset.studentIndex);

        const student =
            students[studentIndex];

        openStudentDrawer(student);

    });

});

        /*
         * =========================
         * SHOW DASHBOARD
         * =========================
         */

        dashboard.classList.remove("hidden");

        /*
         * Hide the old import result panel
         * so the dashboard becomes the main view.
         */

        result.classList.add("hidden");

        dashboard.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });


    } catch (error) {

        result.classList.remove("hidden");

        resultContent.innerHTML = `
            <div class="error">
                ✕ Could not load academic results
            </div>

            <p style="margin-top:15px;color:#999;">
                ${error.message}
            </p>
        `;

    }


    resultsButton.disabled = false;
    resultsButton.textContent = "View Results";

});
const studentDrawerOverlay = document.getElementById("studentDrawerOverlay");
const closeStudentDrawer = document.getElementById("closeStudentDrawer");

function openStudentDrawer(student) {
    document.getElementById("drawerStudentName").textContent =
        student.student_name;

    document.getElementById("drawerRollNo").textContent =
        `Roll No: ${student.roll_no}`;

    document.getElementById("drawerOverallScore").textContent =
        `${student.overall_percentage.toFixed(1)}%`;

    document.getElementById("drawerGrade").textContent =
        student.grade;

    const statusElement = document.getElementById("drawerStatus");

    statusElement.textContent =
        student.passed ? "Passed" : "Failed";

    statusElement.className =
        student.passed ? "drawer-passed" : "drawer-failed";

    const courses = student.course_results || [];

    document.getElementById("drawerCourses").innerHTML =
        courses.map(course => `
            <div class="drawer-course">
                <div class="drawer-course-header">
                    <strong>${course.course_name}</strong>
                    <span>${course.percentage.toFixed(1)}%</span>
                </div>

                <div class="drawer-marks">
                    <div>
                        <span>Internal</span>
                        <strong>${course.component_scores?.Internal ?? "-"}</strong>
                    </div>

                    <div>
                        <span>External</span>
                        <strong>${course.component_scores?.External ?? "-"}</strong>
                    </div>

                    <div>
                        <span>Grade</span>
                        <strong>${course.grade}</strong>
                    </div>
                </div>
            </div>
        `).join("");

    studentDrawerOverlay.classList.remove("hidden");
}

function closeDrawer() {
    studentDrawerOverlay.classList.add("hidden");
}

closeStudentDrawer.addEventListener("click", closeDrawer);

studentDrawerOverlay.addEventListener("click", (event) => {
    if (event.target === studentDrawerOverlay) {
        closeDrawer();
    }
});
// ===============================
// STUDENT DETAILS DRAWER
// ===============================
