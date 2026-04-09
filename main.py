from flask import Flask, flash, render_template, request, redirect, url_for, session, jsonify
from postgrest.exceptions import APIError
from supabase import create_client, Client
from dotenv import load_dotenv
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

# Normal client (anon key)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Admin client (service role key)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

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
    public_link = url_for("teacher_page", username=username, _external=True)
    dashboard_link = url_for("dashboard", user_id=user_id, _external=True)

    # Generated link
    #link = url_for("teacher_page", username=username, _external=True)

    return f"""
    <div class="fixed inset-0 flex items-center justify-center bg-gray-800 bg-opacity-50">
      <div class="bg-white rounded-lg shadow-lg p-6 w-96">
        <h2 class="text-1xl font-bold mb-4">Congrats on successfully registering!</h2>
        <p class="mb-2">Here are your access links:</p>
        <p class="mt-4 mb-2">Public page (share this):</p>
        <a href="{public_link}" target="_blank" class="text-blue-600 underline">{public_link}</a>

        <p class="mt-4 mb-2">Private dashboard (keep this safe):</p>
        <a href="{dashboard_link}" target="_blank" class="text-green-600 underline">{dashboard_link}</a>

        <div class="mt-6 text-right">
          <button class="bg-red-600 text-white px-4 py-2 rounded"
                  onclick="this.closest('div.fixed').remove()">Close</button>
        </div>
      </div>
    </div>
    """

# import time

# @app.before_request
# def refresh_token_if_needed():
#     if "refresh_token" not in session:
#         return

#     # Store when the token was issued
#     if "token_timestamp" not in session:
#         session["token_timestamp"] = time.time()

#     # If more than 45 minutes have passed, refresh
#     if time.time() - session["token_timestamp"] > 45 * 60:
#         try:
#             refreshed = supabase.auth.refresh_session(session["refresh_token"])
#             if refreshed and refreshed.session:
#                 session["access_token"] = refreshed.session.access_token
#                 session["refresh_token"] = refreshed.session.refresh_token
#                 session["token_timestamp"] = time.time()
#                 app.logger.info("Access token refreshed automatically.")
#         except Exception as e:
#             app.logger.error(f"Token refresh failed: {e}")
#             # Optionally clear session or force re-login


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
                # Decode JWT to verify sub
                decoded = jwt.decode(
                    result.session.access_token,
                    options={"verify_signature": False}
                )
                token_uid = decoded.get("sub")

                app.logger.info(f"Supabase user.id: {result.user.id}, JWT sub: {token_uid}")

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

                flash("Login successful", "success")
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid credentials", "error")
                return redirect(url_for("login"))

        except Exception as e:
            app.logger.error(f"Login error: {e}")
            flash("Something went wrong during login.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")



@app.route("/logout")
def logout():
    supabase.auth.sign_out()
    session.clear()
    return redirect(url_for("login"))

def send_email(to, subject, body):
    # integrate with mail provider here
    pass

@app.route("/book/<slot_id>", methods=["POST"])
def book_slot(slot_id):
    learner_email = request.form.get("learner_email")
    slot = supabase.table("available_slots").select("*").eq("id", slot_id).execute()
    if not slot.data:
        return "Slot not found", 404
    
    room_name = f"class-{uuid.uuid4()}"
    meet_url = f"https://meet.jit.si/{room_name}"

    booking = supabase.table("teacher_bookings").insert({
        "trainer_id": slot.data[0]["trainer_id"],
        "learner_email": learner_email,
        "course_name": slot.data[0]["course_name"],
        "scheduled_at": slot.data[0]["slot"],
        "meet_url": meet_url
    }).execute()

    # Fetch teacher email
    teacher = supabase.table("teacher_profiles").select("username").eq("id", slot.data[0]["trainer_id"]).execute()
    teacher_email = supabase.auth.get_user().user.email  # or store in teacher_profiles

    # Send emails
    send_email(learner_email, "Your Class Booking", f"Join your class here: {meet_url}")
    send_email(teacher_email, "New Booking", f"A learner booked your class. Meeting link: {meet_url}")

    return f"Booking confirmed! Join here: <a href='{meet_url}'>{meet_url}</a>"



@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    response = supabase.auth.get_user()
    slots = supabase.table("available_slots").select("*").eq("trainer_id", session["user_id"]).execute()
    bookings = supabase.table("teacher_bookings").select("*").eq("trainer_id", session["user_id"]).execute()
    #return f"<h1>Welcome {session['email']}</h1><a href='/logout'>Logout</a>"
    return render_template("dashboard.html", email=session['email'], user=response.user.user_metadata, slots=slots.data, bookings=bookings.data)
    #return f"<h1>Welcome {session['username']}</h1><a href='/logout'>Logout</a>"

# @app.route("/dashboard/slots/add", methods=["POST"])
# def add_slot():
#     user_client = get_user_client()
#     if not user_client:
#         flash("You must be logged in to add a slot", "error")
#         return redirect(url_for("login"))
    
#     course_name = request.form.get("course_name")
#     course_duration = request.form.get("course_duration")
#     slot = request.form.get("slot")  # ISO datetime string

#     user_client.table("available_slots").insert({
#         "trainer_id": session["user_id"],
#         "course_name": course_name,
#         "course_duration": course_duration,
#         "slot": slot
#     }).execute()
#     flash("Slot added successfully", "success")
#     return redirect(url_for("list_slots"))

@app.route("/dashboard/slots/add", methods=["POST"])
def add_slot():
    user_client = get_user_client()
    print(f"Session user_id: {session.get('user_id')}")
    if not user_client:
        flash("You must be logged in to add a slot", "error")
        return redirect(url_for("login"))
    
    course_name = request.form.get("course_name")
    course_duration = request.form.get("course_duration")
    course_price = request.form.get("course_price")
    course_description = request.form.get("course_description")
    course_requirements = request.form.get("course_requirements")
    slot = request.form.get("slot")  # ISO datetime string

    try:
        result = user_client.table("available_slots").select("*").execute()
        app.logger.info(f"Select result: {result}")
    except Exception as e:
        app.logger.error(f"Select failed: {e}")    

    try:
        user_client.table("available_slots").insert({
            "trainer_id": session["user_id"],
            "course_name": course_name,
            "course_duration": course_duration,
            "course_price": course_price,
            "course_description": course_description,
            "course_requirements": course_requirements,
            "slot": slot
        }).execute()
        flash("Slot added successfully", "success")
    except APIError as e:
        # Log the error internally for debugging
        app.logger.error(f"Slot insert failed: {e}")
        # Show a friendly message to the user
        flash("Could not add slot due to permissions. Please check your account.", "error")

    return redirect(url_for("dashboard"))


@app.route("/dashboard/slots/edit/<slot_id>", methods=["GET"])
def edit_slot(slot_id):
    slot = supabase.table("available_slots").select("*").eq("id", slot_id).execute()
    if not slot.data:
        return "Slot not found", 404
    slot = slot.data[0]
    return f"""
    <form hx-post="/dashboard/slots/update/{slot['id']}" hx-target="#slot-{slot['id']}" hx-swap="outerHTML">
      <input type="text" name="course_name" value="{slot['course_name']}" class="border p-1 rounded">
      <input type="number" name="course_duration" value="{slot['course_duration']}" class="border p-1 rounded">
      <input type="number" name="course_price" value="{slot['course_price']}" class="border p-1 rounded">
      <input type="text" name="course_description" value="{slot['course_description']}" class="border p-1 rounded">
      <input type="text" name="course_requirements" value="{slot['course_requirements']}" class="border p-1 rounded">
      <input type="datetime-local" name="slot" value="{slot['slot']}" class="border p-1 rounded">
      <button type="submit" class="bg-green-500 text-white px-2 py-1 rounded">Save</button><br/>
    <span class="htmx-indicator ml-2 text-sm text-green-500">⏳ Saving...</span>
    </form>
    """

@app.route("/dashboard/slots/update/<slot_id>", methods=["POST"])
def update_slot(slot_id):
    course_name = request.form.get("course_name")
    course_duration = request.form.get("course_duration")
    course_price = request.form.get("course_price")
    course_description = request.form.get("course_description")
    course_requirements = request.form.get("course_requirements")
    slot_time = request.form.get("slot")
    supabase.table("available_slots").update({
        "course_name": course_name,
        "course_duration": course_duration,
        "course_price": course_price,
        "course_description": course_description,
        "course_requirements": course_requirements,
        "slot": slot_time
    }).eq("id", slot_id).execute()

    return f"<span id='slot-{slot_id}'>{course_name} — {slot_time} - {course_duration} </span>"


@app.route("/dashboard/slots/delete/<slot_id>", methods=["POST"])
def delete_slot(slot_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    supabase.table("available_slots").delete().eq("id", slot_id).execute()
    return redirect(url_for("dashboard"))



@app.route("/<username>")
def teacher_page(username):
    result = supabase.table("teacher_profiles").select("*").eq("username", username).execute()
    if result.data:
        profile = result.data[0]
        slots = supabase.table("available_slots").select("*").eq("trainer_id", result.data[0]["id"]).execute()
        return render_template("trainer.html", profile=profile, slots=slots.data)
    return "Teacher not found", 404

@app.route("/update_account", methods=["POST"])
def update_account():
    if "user_id" not in session:
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
    supabase.auth.update_user(update_data)

    # Update teacher_profiles table
    supabase.table("teacher_profiles").update({
        "username": new_username,
        "bio": new_bio
    }).eq("id", session["user_id"]).execute()

    # Handle password reset if provided
    if new_password:
        supabase.auth.update_user({"password": new_password})

    return redirect(url_for("dashboard"))


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
@app.route("/delete_account", methods=["POST"])
def delete_account():
    if "user_id" not in session:
        flash("You must be logged in to delete your account.", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]

    try:
        # Delete dependent rows
        supabase.table("profiles").delete().eq("id", user_id).execute()
        supabase.table("teacher_profiles").delete().eq("id", user_id).execute()

        # Delete Auth user
        supabase_admin.auth.admin.delete_user(user_id)

        session.clear()
        flash("Your account has been deleted successfully.", "success")
        return redirect(url_for("landing_page"))

    except Exception as e:
        app.logger.error(f"Delete account error: {e}")
        flash("We couldn’t delete your account. Please contact support.", "error")
        return redirect(url_for("dashboard"))


@app.route("/confirm_delete", methods=["GET"])
def confirm_delete():
    print("Confirm delete..")
    if "user_id" not in session:
        return "<p class='text-red-600'>You must be logged in.</p>"

    return """
    <div class="fixed inset-0 flex items-center justify-center bg-gray-800 bg-opacity-50" style="display:flex;flex-direction:column;justify-content:center;align-items:center;padding:4px;">
      <div class="bg-white rounded-lg shadow-lg p-6 w-96">
        <h2 class="text-xl font-bold mb-4">Confirm Deletion</h2>
        <p class="mb-4">Are you sure you want to delete your account? This action cannot be undone.</p>
        <div class="flex justify-end space-x-4">
          <button class="bg-gray-400 text-white px-4 py-2 rounded"
                  onclick="this.closest('div.fixed').remove()" style="background-color:black;color:white;padding:6px;margin:6px;">Cancel</button>
          <form action="/delete_account" method="post" hx-target="#modal-container" hx-swap="innerHTML">
            <button type="submit" class="bg-red-500 text-white px-4 py-2 rounded" style="background-color:red;color:white;padding:6px;margin:6px;">Delete</button>
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
