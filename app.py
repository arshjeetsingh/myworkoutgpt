from flask import Flask, request, render_template, redirect, url_for, session
import mysql.connector
import requests
import openai
from datetime import datetime, timedelta
from openai import OpenAI
import os
import time
import pandas as pd



#Initialize the OpenAI client with your API key
# openai.api_key = "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" #(for openai0.28)
client = OpenAI(
  api_key='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',
)

# Initialize Flask application
app = Flask(__name__)
# Enable debug mode for easier troubleshooting during development
app.config['DEBUG'] = True
app.secret_key = 'gbhwV3PosdBlCrqlZWS5dA'

# Strava API and OpenAI API credentials
client_id = '122577'
client_secret = '9b3d6bb1d8aa8dbd537dfe270d8b1c10ee81e606'
openai_api_key = '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'
assistant_id = 'asst_x3kMlwfdACiMtfaXjqH9mnSU'

# Set OpenAI API key for usage in the app
# openai.api_key = openai_api_key

# Variables for managing Strava access tokens
access_token = None
refresh_token = None
expiration_time = None
auth_url = ''
activities = None


def convert_seconds(total_seconds):
    """Converts seconds into hours, minutes, and seconds."""
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return hours, minutes, seconds

def parse_auth_code():
    '''Function to parse the authorization code directly from Flask request,
    ensuring it has both "profile:read_all" and "activity:read_all" permissions.'''
    scope_values = request.args.get('scope', None)
    scopes = scope_values.split(',') if scope_values else []
    # Check for both required scopes
    required_scopes = ['profile:read_all', 'activity:read_all']
    if all(scope in scopes for scope in required_scopes):
        return request.args.get('code', None)
    else:
        return None

def obtain_tokens(auth_code):
    """Obtains Strava access and refresh tokens using an authorization code."""
    global access_token, refresh_token, expiration_time

    # API endpoint to request tokens
    url = 'https://www.strava.com/api/v3/oauth/token'

    # Data payload for token request
    data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': auth_code,
        'grant_type': 'authorization_code'
    }

    # Send POST request to obtain tokens
    response = requests.post(url, data=data)
    response_data = response.json()

    if response.status_code == 200:
        # Extract tokens and set expiration time
        access_token = response_data["access_token"]
        refresh_token = response_data["refresh_token"]
        expires_in = response_data["expires_in"]
        expiration_time = datetime.now() + timedelta(seconds=expires_in)
        return access_token, refresh_token
    else:
        raise Exception(f"Error obtaining tokens: {response.text}")

def refresh_strava_access_token_if_needed():
    """Refreshes the Strava access token if it has expired."""
    global access_token, refresh_token, expiration_time

    # Check if the access token needs to be refreshed
    if not access_token or not expiration_time or datetime.now() >= expiration_time:
        response = requests.post(
            'https://www.strava.com/oauth/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token
            }
        )
        # If the request is successful (status code 200)
        if response.status_code == 200:
            # Parse the response JSON
            tokens = response.json()

            # Update the access token, refresh token, and expiration time
            access_token = tokens['access_token']
            refresh_token = tokens['refresh_token']
            expiration_time = datetime.now() + timedelta(seconds=tokens['expires_in'])
        else:
            # Raise an exception if the token refresh fails
            raise Exception(f"Failed to refresh Strava access token: {response.text}")

def fetch_strava_activities():
    """Fetches the latest Strava activities for the authorized user."""
    global access_token, refresh_token, expiration_time
    refresh_strava_access_token_if_needed()

    activities = []
    page = 1
    per_page = 200  # Maximum activities per page as allowed by the API

    while True:  # Loop until break is called
        response = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"per_page": per_page, "page": page}
        )

        # Check for successful response
        if response.status_code == 200:
            page_activities = response.json()

            # Break the loop if no activities are found, indicating the end
            if not page_activities:
                break

            activities.extend(page_activities)  # Add current page's activities to the list

            # If the number of activities is less than per_page, this is the last page, may need to be removed
            if len(page_activities) < per_page:
                break

            page += 1
        else:
            raise Exception(f"Failed to fetch Strava activities, status code: {response.status_code}")

    return activities

def fetch_strava_profile():
    """Fetches the latest Strava profile for the authorized user."""
    refresh_strava_access_token_if_needed()
    response = requests.get("https://www.strava.com/api/v3/athlete", headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code == 200:
        profile_data = response.json()
        print("Profile data fetched:", profile_data)  # Debugging line
        return profile_data
    else:
        print(f"Failed to fetch Strava profile: {response.status_code}, {response.text}")
        return None

    
def insert_strava_profile(profile_data):
    if not profile_data:
        print("No profile data provided for insertion.")
        return None

    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            # Make sure the column names and values match the table schema in MySQL
            cursor.execute("""
                INSERT INTO StravaProfiles (user_id, username, firstname, lastname, city, state, country, sex, premium, created_at, updated_at, badge_type_id, profile_medium, profile, follower_count, friend_count, mutual_friend_count, athlete_type, date_preference, measurement_preference, ftp, weight)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                profile_data.get('id'),
                profile_data.get('username'),
                profile_data.get('firstname'),
                profile_data.get('lastname'),
                profile_data.get('city'),
                profile_data.get('state'),
                profile_data.get('country'),
                profile_data.get('sex'),
                profile_data.get('premium'),
                profile_data.get('badge_type_id'),
                profile_data.get('profile_medium'),
                profile_data.get('profile'),
                profile_data.get('follower_count'),
                profile_data.get('friend_count'),
                profile_data.get('mutual_friend_count'),
                profile_data.get('athlete_type'),
                profile_data.get('date_preference'),
                profile_data.get('measurement_preference'),
                profile_data.get('ftp'),
                profile_data.get('weight'),
            ))
            conn.commit()
        except mysql.connector.Error as err:
            print(f"Error inserting Strava profile into the database: {err}")
            return None
        finally:
            cursor.close()
            conn.close()
        return profile_data.get('id')  # After successful insertion
    else:
        print("Failed to establish database connection.")
        return None


    
def insert_strava_activities(activities, user_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            for activity in activities:
                # Create a unique identifier for the activity
                unique_id = (user_id, activity.get('start_date'), activity.get('name'))

                # Check if the activity already exists based on the unique identifier
                cursor.execute("""
                    SELECT COUNT(*) FROM StravaActivities 
                    WHERE user_id = %s AND start_date = %s AND name = %s
                """, unique_id)
                result = cursor.fetchone()

                if result[0] > 0:
                    # Activity already exists, skip to the next one
                    continue

                # Prepare data for insertion, ensure this matches your table schema
                data = (
                    user_id,  # Ensure this is the correct user ID
                    activity.get('name', ''),
                    float(activity.get('distance', 0)),
                    activity.get('moving_time', 0),
                    activity.get('elapsed_time', 0),
                    float(activity.get('total_elevation_gain', 0)),
                    activity.get('type', ''),
                    activity.get('start_date', ''),
                    activity.get('start_date_local', ''),
                    activity.get('timezone', ''),
                    activity.get('location_country', ''),
                    activity.get('achievement_count', 0),
                    activity.get('kudos_count', 0),
                    activity.get('comment_count', 0),
                    activity.get('athlete_count', 0),
                    activity.get('photo_count', 0),
                    activity.get('trainer', False),
                    activity.get('commute', False),
                    activity.get('manual', False),
                    activity.get('private', False),
                    activity.get('visibility', ''),
                    activity.get('flagged', False),
                    float(activity.get('average_speed', 0)),
                    float(activity.get('max_speed', 0)),
                    activity.get('has_heartrate', False),
                    activity.get('heartrate_opt_out', False),
                    activity.get('display_hide_heartrate_option', False),
                    float(activity.get('elev_high', 0)),
                    float(activity.get('elev_low', 0)),
                    activity.get('pr_count', 0),
                    activity.get('total_photo_count', 0)
                )

                # Insert the new activity
                cursor.execute("""
                    INSERT INTO StravaActivities (
                        user_id, name, distance, moving_time, elapsed_time, total_elevation_gain,
                        activity_type, start_date, start_date_local, timezone, location_country,
                        achievement_count, kudos_count, comment_count, athlete_count, photo_count,
                        trainer, commute, manual, private, visibility, flagged, average_speed,
                        max_speed, has_heartrate, heartrate_opt_out, display_hide_heartrate_option,
                        elev_high, elev_low, pr_count, total_photo_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, data)
                conn.commit()
        except mysql.connector.Error as err:
            print(f"Error inserting Strava activities: {err}")
        finally:
            cursor.close()
            conn.close()


def preprocess_strava_activities(activities):
    preprocessed_activities = []
    for activity in activities:
        preprocessed_activity = {
            'name': activity.get('name', ''),
            'distance': float(activity.get('distance', 0)),
            'moving_time': int(activity.get('moving_time', 0)),
            'elapsed_time': int(activity.get('elapsed_time', 0)),
            'total_elevation_gain': float(activity.get('total_elevation_gain', 0)),
            'activity_type': activity.get('type', ''),
            'start_date': convert_to_datetime_format(activity.get('start_date')),
            'start_date_local': convert_to_datetime_format(activity.get('start_date_local')),
            'timezone': activity.get('timezone', ''),
            'location_country': activity.get('location_country', ''),
            'achievement_count': int(activity.get('achievement_count', 0)),
            'kudos_count': int(activity.get('kudos_count', 0)),
            'comment_count': int(activity.get('comment_count', 0)),
            'athlete_count': int(activity.get('athlete_count', 0)),
            'photo_count': int(activity.get('photo_count', 0)),
            'trainer': bool(activity.get('trainer', False)),
            'commute': bool(activity.get('commute', False)),
            'manual': bool(activity.get('manual', False)),
            'private': bool(activity.get('private', False)),
            'visibility': activity.get('visibility', ''),
            'flagged': bool(activity.get('flagged', False)),
            'average_speed': float(activity.get('average_speed', 0)),
            'max_speed': float(activity.get('max_speed', 0)),
            'has_heartrate': bool(activity.get('has_heartrate', False)),
            'heartrate_opt_out': bool(activity.get('heartrate_opt_out', False)),
            'display_hide_heartrate_option': bool(activity.get('display_hide_heartrate_option', False)),
            'elev_high': float(activity.get('elev_high', 0)),
            'elev_low': float(activity.get('elev_low', 0)),
            'pr_count': int(activity.get('pr_count', 0)),
            'total_photo_count': int(activity.get('total_photo_count', 0)),
        }
        preprocessed_activities.append(preprocessed_activity)
    return preprocessed_activities

def convert_to_datetime_format(strava_date):
    """Strava date format is ISO 8601 (YYYY-MM-DDTHH:MM:SSZ), convert to MySQL datetime format"""
    from datetime import datetime
    if strava_date:
        return datetime.strptime(strava_date, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d %H:%M:%S')
    return None



def get_db_connection():
    """Establishes a connection to the MySQL database."""
    try:
        return mysql.connector.connect(
            user='root', password='Root@123', host='localhost', database='myappdb'
        )
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

def insert_message(name, email, message):
    """Inserts a message for a user. If the user does not exist, creates the user."""
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(buffered=True)
        try:
            # Check if user exists
            cursor.execute("SELECT user_id FROM Users WHERE name = %s AND email = %s", (name, email))
            result = cursor.fetchone()

            if result:
                user_id = result[0]
            else:
                # Insert new user
                cursor.execute("INSERT INTO Users (name, email) VALUES (%s, %s)", (name, email))
                user_id = cursor.lastrowid
                conn.commit()

            # Insert new message linked to the user_id
            cursor.execute("INSERT INTO Messages (user_id, message) VALUES (%s, %s)", (user_id, message))
            conn.commit()

        except mysql.connector.Error as err:
            print(f"Error: {err}")
            return None
        finally:
            cursor.close()
            conn.close()
        return user_id
    
    
def save_activities_to_excel(activities, file_path="strava_activities.csv"):
    activities_df = pd.DataFrame(activities)
    print(f"Saving {len(activities)} activities to {file_path}")  # Debugging line
    activities_df.to_csv(file_path, index=False)  # Note: changed to_csv for CSV file


            
def upload_file_to_openai(file_path):
    try:
        with open(file_path, "rb") as reader:
            response = client.files.create(file=reader, purpose='assistants')
            file_id = response.id
            session['file_id'] = file_id
            print(f"File uploaded to OpenAI, File ID: {file_id}")  # Confirm file_id is not None
            return file_id
    except openai.OpenAIError as e:
        print(f"Failed to upload file to OpenAI: {e}")
        return None

def run_assistant(thread_id, assistant_id):
    # Start the assistant run on the given thread
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
    )
    
    # Loop until the run's status is 'completed'
    while True:
        # Retrieve the latest status of the run
        run_status = client.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        ).status
        
        # Check if the run is completed
        if run_status == "completed":
            break  # Exit the loop if the run is completed
        
        # Optionally, add a delay to reduce the frequency of API calls
        time.sleep(0.5)  # Adjust the sleep time as needed

    # Once the run is completed, retrieve the final message from the assistant
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    
    # Assuming the latest assistant's message is what we're interested in
    # This might need adjustment based on your exact needs
    final_message = messages.data[-1].content  # Adjust based on how messages are structured
    
    return final_message

def query_openai_assistant(user_question, assistant_id, file_id=None):
    try:
        # Create a new thread
        thread_response = client.beta.threads.create()
        print(f"Thread created: {thread_response}")
        thread_id = thread_response.id
        file_id = session.get('file_id', None)
        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_question, file_ids=[file_id])
        # Modify user_question if file_id is provided
        # user_question = f"{user_question} [file_id={file_id}]" if file_id else user_question
        runs = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
        runs = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=runs.id)

        # Submit the user's question as a message
        
        # Wait for the assistant's response with a more robust mechanism
        end_time = time.time() + 100  # Wait for up to 10 seconds
        while time.time() < end_time:
            messages = client.beta.threads.messages.list(thread_id=thread_id, order="asc")
            for message in messages.data:
                # Debugging: print all received messages
                print("Received message:", message)
                # Check if the message is from the assistant
                if message.role != 'user':
                    for content_block in message.content:
                        # Check if this block contains text
                        if content_block.type == 'text':
                            assistant_response = content_block.text.value
                            return assistant_response.strip()
            time.sleep(1)  # Check every second for the assistant's response

        return "Assistant's response not found."
    except Exception as e:
        print(f"An error occurred: {e}")
        return "An error occurred during the query."




@app.route('/')
def index():
    """Renders the homepage."""
    answer = session.pop('answer', None)
    thank_you_message = session.pop('thank_you_message', None)
    error_message = session.pop('error_message', None)
    return render_template('index.html', answer=answer, thank_you_message=thank_you_message, error_message=error_message)


@app.route('/query', methods=['POST'])
def query_activities():
    user_question = request.form.get('question', '').strip()
    file_id = session.get('file_id', None)

    print(f"Question: {user_question}, File ID: {file_id}")  # Debugging
    if not user_question:
        session['answer'] = "Please provide a question."
    elif not file_id:
        session['answer'] = "File ID not available, but proceeding with question."
        # Here, even if file ID is not available, we can still ask questions without context.
    else:
        # Existing code to fetch response
        try:
            if not refresh_token:
                answer="Please Authorize your Strava Account first"
                session['answer'] = answer
                return redirect(url_for('index'))
            assistant_response = query_openai_assistant(user_question, assistant_id)
            print(f"Assistant's response: {assistant_response}")  # Additional debugging
            session['answer'] = assistant_response
        except Exception as e:
            print(f"Error querying OpenAI: {e}")
            session['answer'] = f"Error querying the OpenAI API: {str(e)}"

    return redirect(url_for('index'))



@app.route('/exchange_token')
def exchange_token():
    global access_token, refresh_token, expiration_time
    auth_code = parse_auth_code()
    if not auth_code:
        session['answer'] = 'Please authorize access to both your Strava activities and profile by logging into your account.'
        return redirect(url_for('index'))
    try:
        obtain_tokens(auth_code)
        activities = fetch_strava_activities()
        if activities:
            preprocessed_activities = preprocess_strava_activities(activities)
            if preprocessed_activities:
                excel_file_path = "strava_activities.csv"
                save_activities_to_excel(preprocessed_activities, excel_file_path)  # Save activities as Excel

                # Attempt to upload the Excel file to OpenAI
                file_id = upload_file_to_openai(excel_file_path)  # Use the correct file path
                session['file_id'] = file_id

                # Use the profile ID from the profile data as the user_id for activities.
                # This assumes the profile ID is the linking field. Adjust if your implementation differs.
                profile_data = fetch_strava_profile()
                if profile_data:
                    insert_strava_profile(profile_data)
                    user_id = profile_data['id']
                    insert_strava_activities(preprocessed_activities, user_id)

                return redirect(url_for('index'))
            else:
                session['answer'] = "Failed to preprocess Strava activities."
                return redirect(url_for('index'))
        else:
            session['answer'] = "No Strava activities could be fetched."
            return redirect(url_for('index'))
    except Exception as e:
        session['answer'] = f"An error occurred: {e}"
        return redirect(url_for('index'))



@app.route('/submit_form', methods=['POST'])
def submit_form():
    """Handles submission of the contact form."""
    name = request.form.get('name')
    email = request.form.get('email')
    message = request.form.get('message')
    user_id = insert_message(name, email, message)
    if user_id:
        session['thank_you_message'] = "Thank you for your submission!"
    else:
        session['error_message'] = "Failed to submit your information."
    return redirect(url_for('index'))
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
