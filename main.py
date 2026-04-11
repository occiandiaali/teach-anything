from flask import Flask, flash, render_template, request, redirect, url_for, session, jsonify
from postgrest.exceptions import APIError
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime

import os
import uuid
import jwt, time

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")  # replace with a secure random key

# Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

DOMAIN = os.getenv("DOMAIN")

# Normal client (anon key)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Admin client (service role key)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# # Future use?
# # Suppose slot["slot"] is an ISO string
# slot_time = datetime.fromisoformat(slot["slot"].replace("Z", "+00:00"))

# # Now you can do calculations
# if slot_time < datetime.utcnow():
#     status = "Expired"
# else:
#     status = "Upcoming"

# pip install sendgrid
# from sendgrid import SendGridAPIClient
# from sendgrid.helpers.mail import Mail

# SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")

# def send_email(to_email, subject, body):
#     message = Mail(
#         from_email="your_verified_sender@example.com",
#         to_emails=to_email,
#         subject=subject,
#         plain_text_content=body
#     )
#     try:
#         sg = SendGridAPIClient(SENDGRID_API_KEY)
#         response = sg.send(message)
#         return response.status_code
#     except Exception as e:
#         print(e)
#         return None

from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("You must be logged in to access this page.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.template_filter("format_datetime")
def format_datetime(value, fmt="%A, %d %B %Y at %I:%M %p"):
    if isinstance(value, str):
        # Convert ISO string to datetime
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.strftime(fmt)

def parse_slot(slot_str):
    # Supabase returns ISO8601 with Z for UTC
    return datetime.fromisoformat(slot_str.replace("Z", "+00:00"))


@app.route("/", methods=["GET"])
def landing_page():
    return render_template("index.html")

@app.route("/register", methods=["POST"])
def register_teacher():
    username = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")
    bio = request.form.get("bio", "")

    # Check if username already exists
    existing = supabase.table("teacher_profiles").select("id").eq("username", username).execute()
    if existing.data:
        return """
        <p class="text-red-600">That username is already taken. Please choose another.</p>
        """


    # Create user in Supabase Auth with metadata
    user = supabase.auth.sign_up({
        "email": email,
        "password": password,
        "options": {
            "data": {  # metadata stored in auth.users
                "username": username,
                "bio": bio
            }
        }
    })
    user_id = user.user.id

    # Insert into teacher_profiles
    supabase.table("teacher_profiles").insert({
        "id": user_id,
        "username": username,
        "bio": bio
    }).execute()

        # Generate links
    # public_link = url_for("teacher_page", username=username, _external=True)
    # dashboard_link = url_for("dashboard", user_id=user_id, _external=True)

    public_link = f"{DOMAIN}/{username}"
    dashboard_link = f"{DOMAIN}/{username}/dashboard"


    # Generated link
    #link = url_for("teacher_page", username=username, _external=True)

    # send_email(
    #     email,
    #     "Your TeachAnything Links",
    #     f"""
    #     Welcome {username}!

    #     Public page (share this):
    #     {public_link}

    #     Private dashboard (keep this safe):
    #     {dashboard_link}

    #     Happy teaching!
    #     """
    # )


    return f"""
    <div class="fixed inset-0 flex items-center justify-center bg-gray-800 bg-opacity-50">
      <div class="bg-white rounded-lg shadow-lg p-6 w-96">
        <h2 class="text-1xl font-bold mb-4">Congrats on successfully registering!</h2>
        <p>You're now well on your way to earning good money by teaching what you know.</p>
        <p>Visit your Private Dashboard to complete setting-up your account..</p><br/>
        <hr/>
        <p class="mb-2">Here are your access links:</p>
        <p class="mt-4 mb-2">Public page (share this):</p>
        <div class="flex items-center space-x-1">
        <a id="public-link" href="{public_link}" target="_blank" class="text-blue-600 underline">
        {public_link}
        </a>
        <button onclick="navigator.clipboard.writeText({public_link})" 
                class="text-gray-500 hover:text-gray-700 cursor-pointer">
        📋
        </button>

        </div>

        <p class="mt-2 mb-2">Private dashboard (keep this safe):</p>
        <div class="flex items-center space-x-1">

        <a id="dashboard-link" href="{dashboard_link }" target="_blank" class="text-green-600 underline">
        { dashboard_link }
        </a>
        <button onclick="navigator.clipboard.writeText({dashboard_link})" 
                class="text-gray-500 hover:text-gray-700 cursor-pointer">
        📋
        </button>

        </div>

        <div class="mt-4 text-right">
          <button class="bg-red-600 text-white px-4 py-2 rounded"
                  onclick="this.closest('div.fixed').remove()">Close</button>
        </div>
      </div>
    </div>
    """

def get_user_client():
    if "access_token" not in session or "refresh_token" not in session:
        return None

    client = create_client(SUPABASE_URL, SUPABASE_KEY)

    try:
        client.auth.set_session(session["access_token"], session["refresh_token"])
        #user = client.auth.get_user()
        #app.logger.info(f"Client user: {user}")

        decoded = jwt.decode(session["access_token"], options={"verify_signature": False})
        app.logger.info(f"JWT sub: {decoded.get('sub')}, session user_id: {session['user_id']}")

        return client
    except Exception as e:
        app.logger.error(f"set_session failed: {e}")
        # If token expired, refresh it
        refreshed = client.auth.refresh_session(session["refresh_token"])
        if refreshed and refreshed.session:
            session["access_token"] = refreshed.session.access_token
            session["refresh_token"] = refreshed.session.refresh_token
            client.auth.set_session(session["access_token"],session["refresh_token"])
            app.logger.info(f"PostgREST session token: {client.postgrest.session}")

            return client
        else:
            return None

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        try:
            result = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            if result.user and result.session:
                decoded = jwt.decode(
                    result.session.access_token,
                    options={"verify_signature": False}
                )
                token_uid = decoded.get("sub")

                if token_uid != result.user.id:
                    app.logger.error("Mismatch between user.id and JWT sub!")
                    flash("Login error: token mismatch", "error")
                    return redirect(url_for("login"))

                # Store verified values in session
                session["user_id"] = result.user.id
                session["email"] = result.user.email
                session["access_token"] = result.session.access_token
                session["refresh_token"] = result.session.refresh_token
                session["token_timestamp"] = time.time()

                # Fetch username for redirect
                profile = supabase.table("teacher_profiles").select("username").eq("id", result.user.id).execute()
                if profile.data:
                    username = profile.data[0]["username"]
                    flash("Login successful", "success")
                    return redirect(url_for("dashboard", username=username))
                else:
                    flash("Profile not found", "error")
                    return redirect(url_for("login"))

            else:
                flash("Invalid credentials", "error")
                return redirect(url_for("login"))

        except Exception as e:
            app.logger.error(f"Login error: {e}")
            flash("Something went wrong during login.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/<username>/dashboard/logout", methods=["GET", "POST"])
@login_required
def logout(username):
    client = get_user_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception as e:
            app.logger.error(f"Logout error: {e}")

    session.clear()

    # Detect if this was an HTMX request
    if request.headers.get("HX-Request") == "true":
        # Return snippet for HTMX swap
        return """
        <p class="text-green-600">You have been logged out successfully.</p>
        <script>
          setTimeout(function() {
            window.location.href = '/login';
          }, 1500);
        </script>
        """
    else:
        # Normal browser request → redirect
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))


def send_email(to, subject, body):
    # integrate with mail provider here
    pass



@app.route("/book/<slot_id>", methods=["POST"])
def book_slot(slot_id):
    learner_email = request.form.get("learner_email")

    # Fetch slot
    slot = supabase.table("course_slots").select("*").eq("id", slot_id).execute()
    if not slot.data:
        return "Slot not found", 404
    slot_data = slot.data[0]

    # Fetch course
    course = supabase.table("courses").select("*").eq("id", slot_data["course_id"]).execute()
    if not course.data:
        return "Course not found", 404
    course_data = course.data[0]

    # Validate slot time
    slot_time = parse_slot(slot_data["slot"])
    if slot_time < datetime.utcnow():
        return "This slot has expired", 400

    # Generate meeting link
    room_name = f"class-{uuid.uuid4()}"
    meet_url = f"https://meet.jit.si/{room_name}"

    # Insert booking
    booking = supabase.table("teacher_bookings").insert({
        "trainer_id": course_data["trainer_id"],
        "learner_email": learner_email,
        "course_id": course_data["id"],
        "slot_id": slot_data["id"],
        "scheduled_at": slot_data["slot"],
        "meet_url": meet_url,
        "status": "pending"
    }).execute()

    # Redirect to payment gateway (placeholder)
    return redirect(url_for("initiate_payment", booking_id=booking.data[0]["id"]))


# =================Payments Flow==========
import requests

PAYSTACK_SECRET_KEY = "sk_test_xxx"  # replace with your real secret key

@app.route("/initiate_payment/<booking_id>")
def initiate_payment(booking_id):
    # Fetch booking details
    booking = supabase.table("teacher_bookings").select("*").eq("id", booking_id).execute()
    if not booking.data:
        return "Booking not found", 404

    booking_data = booking.data[0]

    # Prepare Paystack payload
    payload = {
        "email": booking_data["learner_email"],
        "amount": int(booking_data["course_price"]) * 100,  # Paystack expects kobo
        "reference": f"booking-{booking_id}",
        "callback_url": url_for("payment_callback", booking_id=booking_id, _external=True)
    }

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers)
    data = response.json()

    if not data.get("status"):
        return f"Payment init failed: {data}", 400

    # Redirect learner to Paystack checkout
    return redirect(data["data"]["authorization_url"])

@app.route("/payment_callback/<booking_id>")
def payment_callback(booking_id):
    reference = request.args.get("reference")

    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    response = requests.get(f"https://api.paystack.co/transaction/verify/{reference}", headers=headers)
    data = response.json()

    if data.get("status") and data["data"]["status"] == "success":
        supabase.table("teacher_bookings").update({"status": "confirmed"}).eq("id", booking_id).execute()

        booking = supabase.table("teacher_bookings").select("*").eq("id", booking_id).execute().data[0]
        send_email(booking["learner_email"], "Booking Confirmed", f"Your class is confirmed! Join here: {booking['meet_url']}")
        # Teacher email logic as before

        return "Payment successful! Your booking is confirmed."
    else:
        return "Payment failed or not verified.", 400
#=======================================================Payments end

@app.route("/<username>/dashboard/courses/add", methods=["POST"])
@login_required
def add_course(username):
    user_client = get_user_client()
    profile = user_client.table("teacher_profiles").select("id").eq("username", username).execute()
    if not profile.data or session["user_id"] != profile.data[0]["id"]:
        flash("Unauthorized access.", "error")
        return redirect(url_for("login"))

    course_data = {
        "trainer_id": session["user_id"],
        "course_name": request.form["course_name"],
        "course_duration": request.form["course_duration"],
        "course_price": request.form["course_price"],
        "course_description": request.form["course_description"],
        "course_requirements": request.form["course_requirements"],
    }

    course = user_client.table("courses").insert(course_data).execute().data[0]

    slots = request.form.getlist("slots[]")
    inserts = [{"course_id": course["id"], "slot": s} for s in slots if s]
    if inserts:
        user_client.table("course_slots").insert(inserts).execute()

    flash("Course created successfully", "success")
    return redirect(url_for("dashboard", username=username))

# =========Add slots to existing courses==============
# @app.route("/<username>/dashboard/slots/add/<course_id>", methods=["POST"])
# @login_required
# def add_slot(username, course_id):
#     user_client = get_user_client()
#     slots = request.form.getlist("slots[]")
#     inserts = [{"course_id": course_id, "slot": s} for s in slots if s]
#     if inserts:
#         user_client.table("course_slots").insert(inserts).execute()
#         flash(f"{len(inserts)} slots added", "success")
#     return redirect(url_for("dashboard", username=username))
@app.route("/<username>/dashboard/slots/add/<course_id>", methods=["POST"])
@login_required
def add_slot(username, course_id):
    user_client = get_user_client()
    slots = request.form.getlist("slots[]")
    inserts = [{"course_id": course_id, "slot": s} for s in slots if s]
    if inserts:
        user_client.table("course_slots").insert(inserts).execute()
        #flash(f"{len(inserts)} slots added", "success")

    # Fetch updated course and slots
    course = user_client.table("courses").select("*").eq("id", course_id).execute().data[0]
    slots_for_course = user_client.table("course_slots").select("*").eq("course_id", course_id).execute().data

    # Render the updated course card
    return render_template(
        "partials/course_view.html",
        course=course,
        slots_for_course=slots_for_course,
        username=username
    ) + """
    <div hx-swap-oob="innerHTML:#new-slot-container"></div>
    """


@app.route("/<username>/dashboard/slots/add_form/<course_id>", methods=["GET"])
@login_required
def add_slot_form(username, course_id):
    print("Adding new slot form..")
    client = get_user_client()
    if not client:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("login"))

    # Verify trainer
    profile = client.table("teacher_profiles").select("id").eq("username", username).execute()
    if not profile.data or session["user_id"] != profile.data[0]["id"]:
        return "Unauthorized", 403

    course = client.table("courses").select("*").eq("id", course_id).execute().data
    if not course:
        return "Course not found", 404
    
    print(f"Course: {course}, user: {username}..")

    return render_template("partials/add_slot_form.html", course=course[0], username=username)

@app.route("/<username>/dashboard/courses/view/<course_id>", methods=["GET"])
@login_required
def view_course(username, course_id):
    user_client = get_user_client()
    course = user_client.table("courses").select("*").eq("id", course_id).execute().data
    if not course:
        return "Course not found", 404

    slots_for_course = user_client.table("course_slots").select("*").eq("course_id", course_id).execute().data

    return render_template(
        "partials/course_view.html",
        course=course[0],
        slots_for_course=slots_for_course,
        username=username
    )



#==========Delete and auto-delete slots==============
@app.route("/<username>/dashboard/slots/delete/<slot_id>", methods=["DELETE"])
@login_required
def delete_slot(username, slot_id):
    user_client = get_user_client()
    slot = user_client.table("course_slots").select("*").eq("id", slot_id).execute().data
    if not slot:
        return "Slot not found", 404
    course_id = slot[0]["course_id"]

    user_client.table("course_slots").delete().eq("id", slot_id).execute()
    
        # Auto-delete course if no slots remain
    remaining = user_client.table("course_slots").select("id").eq("course_id", course_id).execute().data
    # if not remaining:
    #     user_client.table("courses").delete().eq("id", course_id).execute()
    #     message = "Course deleted (no slots left)"
    # else:
    #     message = "Slot deleted successfully"

    # #return "", 204
    # # Returns a fragment that HTMX can inject into the status container
    # return f"""
    # <div hx-swap-oob="innerHTML:#status-container">{message}</div>
    # """, 200
    if not remaining:
        user_client.table("courses").delete().eq("id", course_id).execute()
        message = "Course deleted (no slots left)"
        # Return both status message and an OOB swap to clear the course card
        return f"""
        <div hx-swap-oob="innerHTML:#status-container">{message}</div>
        <div hx-swap-oob="outerHTML:#course-{course_id}"></div>
        """, 200
    else:
        message = "Slot deleted successfully"
        return f"""
        <div hx-swap-oob="innerHTML:#status-container">{message}</div>
        """, 200


@app.route("/<username>/dashboard/slots/new_input")
@login_required
def new_slot_input(username):
    client = get_user_client()
    if not client:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("login"))

    # Verify that the logged-in user matches the username in the URL
    profile = client.table("teacher_profiles").select("id").eq("username", username).execute()
    if not profile.data:
        return "Trainer not found", 404

    if session.get("user_id") != profile.data[0]["id"]:
        flash("Unauthorized access to another trainer's dashboard.", "error")
        return redirect(url_for("login"))

    # If authorized, return the input field
    return '<input type="datetime-local" name="slots[]" class="border p-2 rounded w-full" />'


@app.route("/<username>")
def teacher_page(username):
    # public learner page
    profile = supabase.table("teacher_profiles").select("*").eq("username", username).execute()
    if not profile.data:
        return "Trainer not found", 404

    trainer_id = profile.data[0]["id"]

    # Fetch courses for this trainer
    courses = supabase.table("courses").select("*").eq("trainer_id", trainer_id).execute().data

    # Fetch slots for those courses
    slots = supabase.table("course_slots").select("*").in_("course_id", [c["id"] for c in courses]).execute().data

    # Organize slots by course_id for easy lookup in template
    slots_by_course = {}
    for slot in slots:
        slots_by_course.setdefault(slot["course_id"], []).append(slot)

    return render_template(
        "trainer.html",
        profile=profile.data[0],
        courses=courses,
        slots_by_course=slots_by_course
    )



# @app.route("/<username>")
# def teacher_page(username):
#     # public learner page
#     profile = supabase.table("teacher_profiles").select("*").eq("username", username).execute()
#     if not profile.data:
#         return "Trainer not found", 404
#     slots = supabase.table("course_slots").select("*").eq("trainer_id", profile.data[0]["id"]).execute()

#     return render_template("trainer.html", profile=profile.data[0], slots=slots.data)


@app.route("/<username>/dashboard")
@login_required
def dashboard(username):
    client = get_user_client()
    if not client:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("login"))

    # Verify trainer profile
    profile = client.table("teacher_profiles").select("*").eq("username", username).execute()
    if not profile.data:
        return "Trainer not found", 404

    if session.get("user_id") != profile.data[0]["id"]:
        flash("Unauthorized access to another trainer's dashboard.", "error")
        return redirect(url_for("login"))

    trainer_id = profile.data[0]["id"]

    # Fetch all courses for this trainer
    courses = client.table("courses").select("*").eq("trainer_id", trainer_id).execute().data

    # Fetch all slots for these courses
    slots = client.table("course_slots").select("*").in_("course_id", [c["id"] for c in courses]).execute().data

    # Organize slots by course_id for easy lookup in Jinja
    course_slots = {}
    for slot in slots:
        course_slots.setdefault(slot["course_id"], []).append(slot)

    # Fetch bookings as before
    bookings = client.table("teacher_bookings").select("*").eq("trainer_id", trainer_id).execute().data

    # course_bookings = {}
    # for booking in bookings:
    #     course_bookings.setdefault(booking["course_id"], []).append(booking)


    return render_template(
        "dashboard.html",
        user=profile.data[0],
        username=username,
        courses=courses,
        course_slots=course_slots,
        bookings=bookings
    )


@app.route("/<username>/dashboard/update_account", methods=["POST"])
@login_required
def update_account(username):
    client = get_user_client()
    if not client:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("login"))
    
    # Verify that the logged-in trainer matches the username in the URL
    profile = client.table("teacher_profiles").select("id").eq("username", username).execute()
    if not profile.data or session["user_id"] != profile.data[0]["id"]:
        flash("Unauthorized access.", "error")
        return redirect(url_for("login"))

    new_username = request.form.get("username")
    new_password = request.form.get("new_password")
    new_bio = request.form.get("bio")

    # Update metadata in Supabase Auth
    update_data = {
        "data": {
            "username": new_username,
            "bio": new_bio
        }
    }
    client.auth.update_user(update_data)

    # Update teacher_profiles table
    client.table("teacher_profiles").update({
        "username": new_username,
        "bio": new_bio
    }).eq("id", session["user_id"]).execute()

    # Handle password reset if provided
    if new_password:
        client.auth.update_user({"password": new_password})

    return redirect(url_for("dashboard", username=username))


# @app.route("/delete_account", methods=["POST"])
# def delete_account():
#     if "user_id" not in session:
#         flash("You must be logged in to delete your account.", "error")
#         return redirect(url_for("login"))

#     user_id = session["user_id"]

#     # Delete their own profile row (allowed by RLS policy)
#     supabase.table("teacher_profiles").delete().eq("id", user_id).execute()

#     # Delete Auth user (requires service role key)
#     print(f"<<<<<<<<<<<Auth admin about to fire>>>>>>>>>>>>, {user_id}")
#     supabase_admin.auth.admin.delete_user(user_id)
#     print("Account deleted..")


#     # Delete their own auth account (no service role key needed for self-deletion)
#     session.clear()

#     # Flash success message
#     flash("Your account has been deleted successfully.", "success")

#    # return "<p class='text-green-600'>Your account has been deleted successfully.</p>"

#     # Redirect back to 
#     return redirect(url_for("landing_page"))
@app.route("/<username>/dashboard/delete_account", methods=["POST"])
@login_required
def delete_account(username):
    client = get_user_client()
    if not client:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("login"))
    
    # # Verify that the logged-in trainer matches the username in the URL
    # profile = client.table("teacher_profiles").select("id").eq("username", username).execute()
    # if not profile.data or session["user_id"] != profile.data[0]["id"]:
    #     flash("Unauthorized access.", "error")
    #     return redirect(url_for("login"))

    profile = client.table("teacher_profiles").select("id").eq("username", username).execute()

    if not profile.data:
        app.logger.error(f"No profile found for username {username}")
        flash("Profile not found.", "error")
        return redirect(url_for("dashboard", username=username))

    profile_id = str(profile.data[0]["id"])
    session_id = str(session.get("user_id"))

    app.logger.info(f"Session user_id: {session_id}, Profile id: {profile_id}")

    if session_id != profile_id:
        app.logger.error("User mismatch")
        flash("Unauthorized access.", "error")
        return redirect(url_for("dashboard", username=username))



    user_id = session["user_id"]

    try:
        # Delete dependent rows
        client.table("profiles").delete().eq("id", user_id).execute()
        client.table("teacher_profiles").delete().eq("id", user_id).execute()

        # Delete Auth user using Service Key Role
        supabase_admin.auth.admin.delete_user(user_id)

        session.clear()
        flash("Your account has been deleted successfully.", "success")
        return redirect(url_for("landing_page"))

    except Exception as e:
        app.logger.error(f"Delete account error: {e}")
        flash("We couldn’t delete your account. Please contact support.", "error")
        return redirect(url_for("dashboard", username=username))


@app.route("/<username>/dashboard/confirm_delete", methods=["GET"])
@login_required
def confirm_delete(username):
   
    if "user_id" not in session:
        return "<p class='text-red-600'>You must be logged in.</p>"
        

    return f"""
    <div class="fixed inset-0 flex items-center justify-center bg-gray-800 bg-opacity-50" style="display:flex;flex-direction:column;justify-content:center;align-items:center;padding:4px;">
      <div class="bg-white rounded-lg shadow-lg p-6 w-96">
        <h2 class="text-xl font-bold mb-4">Confirm Deletion</h2>
        <p class="mb-4">Are you sure you want to delete your account? This action cannot be undone.</p>
        <div class="flex justify-end space-x-4">
          <button class="bg-gray-400 text-white px-2 py-2 rounded"
                  onclick="this.closest('div.fixed').remove()" style="background-color:black;color:white;padding:6px;margin:6px;border:none;">Cancel</button>
          <form action="/{username}/dashboard/delete_account" method="post" hx-target="#modal-container" hx-swap="innerHTML">
            <button type="submit" class="bg-red-500 text-white px-2 py-2 rounded" style="background-color:red;color:white;padding:6px;margin:6px;border:none;">
            Delete
            <span
          class="htmx-indicator text-white ml-2 hidden">
            ...⏳
            </span>
            </button>
          </form>
        </div>
      </div>
    </div>
    """
# User clicks Delete Account on the dashboard.

# HTMX loads /confirm_delete into #modal-container.

# Modal appears with Cancel and Delete buttons.

# Clicking Delete submits to /delete_account.

# Account is deleted, session cleared, and a success message is shown.


if __name__ == "__main__":
    app.run(debug=True)
