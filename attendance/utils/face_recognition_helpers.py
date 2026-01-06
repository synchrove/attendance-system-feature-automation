# Local model imports
from ..models import AttendanceRecord, Employee, dhaka_now


def debug_request_print(request):
    """Debug utility for API request inspection"""
    print("DEBUG METHOD:", request.method)
    print("DEBUG POST KEYS:", list(request.POST.keys()))
    print("DEBUG FILE KEYS:", list(request.FILES.keys()))


def load_image_from_request(image_file):
    """
    Load and prepare image from mobile app upload.
    
    Process:
    1. Receive image file from mobile app
    2. Convert to RGB format (removes alpha channel)
    3. Prepare for face recognition processing
    
    Returns: PIL Image object in RGB format
    """
    from PIL import Image

    print("DEBUG: image_file name:", image_file.name, "size:", image_file.size)
    img = Image.open(image_file).convert("RGB")
    return img


def detect_face_and_encoding(img):
    """
    Core face detection and encoding generation.
    
    Process:
    1. Convert PIL image to numpy array
    2. Detect face locations using HOG algorithm
    3. Generate 128-dimensional face encoding
    4. Return encoding for matching against database
    
    Features:
    - Uses dlib's face recognition model
    - Handles multiple faces (uses first detected)
    - Returns detailed error messages
    
    Returns: Tuple of (image_array, face_encoding, error_message)
    """
    import numpy as np
    import face_recognition

    img_np = np.array(img)
    print("DEBUG: image shape:", img_np.shape)

    # Detect faces in the image
    face_locations = face_recognition.face_locations(img_np)
    print("DEBUG: num face_locations:", len(face_locations))

    if not face_locations:
        return None, None, "No face detected."

    # Generate 128-d encoding for first detected face
    encoding = face_recognition.face_encodings(img_np, face_locations)[0]
    return img_np, encoding, None


def load_known_encodings():
    """
    Load all registered employee face encodings from database.
    
    Process:
    1. Query employees with valid face encodings
    2. Convert JSON encodings to numpy arrays
    3. Validate encoding format (must be 128-dimensional)
    4. Build parallel lists for matching
    
    Quality Control:
    - Excludes employees without photos
    - Validates encoding dimensions
    - Handles corrupted encoding data gracefully
    
    Returns: Tuple of (encoding_arrays_list, employee_objects_list)
    """
    import numpy as np

    # Get employees with valid face encodings
    employees_qs = Employee.objects.exclude(face_encoding__isnull=True).exclude(
        face_encoding=[]
    )
    print("DEBUG: employees with encoding:", employees_qs.count())

    known_encodings = []
    employees = []

    for emp in employees_qs:
        try:
            # Convert JSON list to numpy array
            arr = np.array(emp.face_encoding, dtype="float32")
            if arr.shape == (128,):  # Validate 128-dimensional encoding
                known_encodings.append(arr)
                employees.append(emp)
        except Exception as e:
            print(f"DEBUG: bad encoding for employee {emp.id}: {e}")
            continue

    return known_encodings, employees


def find_best_match(known_encodings, employees, encoding):
    """
    Advanced face matching with distance-based selection.
    
    Algorithm:
    1. Compare input encoding against all known encodings
    2. Calculate Euclidean distances for similarity
    3. Apply tolerance threshold (0.5 = balanced accuracy)
    4. Select employee with minimum distance (best match)
    
    Features:
    - Tolerance of 0.5 balances false positives/negatives
    - Distance-based ranking for best match selection
    - Comprehensive error handling and logging
    
    Returns: Tuple of (matched_employee, error_message)
    """
    import numpy as np
    import face_recognition

    if not known_encodings:
        print("DEBUG: NO KNOWN ENCODINGS IN DB")
        return None, "No employees with registered face encodings."

    # Compare faces with tolerance threshold
    matches = face_recognition.compare_faces(known_encodings, encoding, tolerance=0.5)
    distances = face_recognition.face_distance(known_encodings, encoding)
    print("DEBUG: matches:", matches)
    print("DEBUG: distances:", distances.tolist())

    if not any(matches):
        print("DEBUG: FACE NOT RECOGNIZED")
        return None, "Face not recognized."

    # Select employee with minimum distance (best match)
    best_index = int(np.argmin(distances))
    employee = employees[best_index]
    print(
        "DEBUG: recognized employee:",
        employee.id,
        employee.employee_id,
        employee.name,
    )
    return employee, None


def mark_attendance(employee, device_id, image_file):
    """
    Smart attendance marking with automatic checkin/checkout logic.
    
    Business Logic:
    1. First recognition of day = CHECK-IN
    2. Second recognition of day = CHECK-OUT
    3. Third+ recognition = Already completed message
    
    Process:
    1. Get or create attendance record for today
    2. Determine check type based on existing timestamps
    3. Save image with appropriate timestamp
    4. Update device_id for tracking
    5. Trigger automatic status calculation
    
    Features:
    - Timezone-aware timestamps (Asia/Dhaka)
    - Image storage with organized naming
    - Device tracking for audit trails
    - Automatic salary recalculation triggers
    
    Returns: Tuple of (check_type, display_message)
    """
    now = dhaka_now()
    today = now.date()

    # Get or create today's attendance record
    record, created = AttendanceRecord.objects.get_or_create(
        employee=employee,
        date=today,
    )
    print("DEBUG: AttendanceRecord pk:", record.pk, "created:", created)

    check_type = None
    display_text = None

    # Rewind file pointer to reuse uploaded file
    try:
        image_file.seek(0)
    except Exception:
        pass

    # Smart check-in/check-out logic
    if record.checkin_time is None:
        # First recognition = CHECK-IN
        record.checkin_time = now
        record.checkin_image = image_file
        record.device_id = device_id or record.device_id
        check_type = "IN"
        display_text = f"Welcome {employee.name}"
        record.save()  # Triggers automatic status calculation
        print("DEBUG: saved CHECK-IN for record", record.pk)

    elif record.checkout_time is None:
        # Second recognition = CHECK-OUT
        record.checkout_time = now
        record.checkout_image = image_file
        record.device_id = device_id or record.device_id
        check_type = "OUT"
        display_text = f"Goodbye {employee.name}"
        record.save()  # Triggers automatic status calculation
        print("DEBUG: saved CHECK-OUT for record", record.pk)

    else:
        # Third+ recognition = Already completed
        check_type = "NONE"
        display_text = f"Attendance already completed today for {employee.name}."
        print("DEBUG: already had IN and OUT for this employee today")

    return check_type, display_text