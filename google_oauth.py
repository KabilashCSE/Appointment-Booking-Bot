import os
import pickle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import gradio as gr

# SCOPES for Google Calendar API
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly', 'https://www.googleapis.com/auth/calendar']

def authenticate_google():
    """Authenticate and return Google Calendar service."""
    creds = None
    try:
        if os.path.exists('token.pickle'):
            try:
                with open('token.pickle', 'rb') as token:
                    creds = pickle.load(token)
                
                if not creds or not creds.valid:
                    if creds and creds.expired and creds.refresh_token:
                        try:
                            creds.refresh(Request())
                        except Exception:
                            os.remove('token.pickle')
                            creds = None
                    else:
                        os.remove('token.pickle')
                        creds = None
            except Exception:
                os.remove('token.pickle')
                creds = None

        if not creds:
            if not os.path.exists('credentials.json'):
                raise FileNotFoundError(
                    "credentials.json file not found. Please download it from Google Cloud Console."
                )
            
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        return build('calendar', 'v3', credentials=creds)

    except Exception as e:
        raise Exception(f"Authentication failed: {str(e)}")

def create_event(service, event_name, start_time, end_time, time_zone='Asia/Kolkata'):
    """Create an event in Google Calendar."""
    try:
        event = {
            'summary': event_name,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': time_zone,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': time_zone,
            },
        }

        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return f'Event "{event_name}" created successfully!'
    except Exception as e:
        error_msg = f"Failed to create event: {str(e)}"
        if "invalid_grant" in str(e):
            if os.path.exists('token.pickle'):
                os.remove('token.pickle')
            error_msg += "\nPlease restart the application to re-authenticate."
        raise Exception(error_msg)

def parse_date_time(date_str, time_str):
    """Parse date and time strings."""
    try:
        date_parts = date_str.split('-')
        if len(date_parts) != 3:
            raise ValueError("Date must be in DD-MM-YYYY format")
        
        day, month, year = map(int, date_parts)
        
        try:
            time_obj = datetime.strptime(time_str.strip().upper(), '%I:%M %p')
        except ValueError:
            raise ValueError("Time must be in HH:MM AM/PM format")

        start_time = datetime(year, month, day,
                            time_obj.hour, time_obj.minute)
        
        return start_time
    except ValueError as e:
        raise ValueError(str(e))

def get_conversation_stage(history):
    """Determine the current stage of the conversation."""
    user_messages = [msg for role, msg in history if role == "User"]
    if not user_messages:
        return 0
    return len(user_messages)

def conversational_flow(history, user_input):
    """Handle the conversation flow with improved input processing."""
    if not user_input:
        return history

    # Check for restart command at any point
    if user_input.lower() in ['restart', 'start over', 'reset']:
        history.clear()
        history.append(("Bot", "Conversation restarted. Hi! How may I assist you?"))
        return history

    # Add user input to history
    history.append(("User", user_input))
    stage = get_conversation_stage(history)

    # Process based on conversation stage
    if stage == 1:  # After first input (Book an appointment)
        if "appointment" in user_input.lower() or "book" in user_input.lower():
            history.append(("Bot", "What is the purpose of the appointment?"))
        else:
            history.pop()  # Remove invalid input
            history.append(("Bot", "I can help you book an appointment. Please say 'Book an appointment' to start."))
    
    elif stage == 2:  # After purpose
        event_name = user_input
        history.append(("Bot", f"Great! You want to create an event for '{event_name}'. What is the date? (DD-MM-YYYY)"))
    
    elif stage == 3:  # After date
        date_str = user_input
        try:
            # Validate date format
            date_parts = date_str.split('-')
            if len(date_parts) != 3 or not all(part.isdigit() for part in date_parts):
                raise ValueError("Date must be in DD-MM-YYYY format")
            history.append(("Bot", "What is the start time? (HH:MM AM/PM)"))
        except ValueError as e:
            history.pop()  # Remove invalid date
            history.append(("Bot", f"Invalid date format: {str(e)}. Please enter the date in DD-MM-YYYY format."))
    
    elif stage == 4:  # After start time
        start_time_str = user_input
        try:
            datetime.strptime(start_time_str.strip().upper(), '%I:%M %p')
            history.append(("Bot", "What is the end time? (HH:MM AM/PM)"))
        except ValueError:
            history.pop()
            history.append(("Bot", "Invalid time format. Please enter the time in HH:MM AM/PM format (e.g., 02:30 PM)."))
    
    elif stage == 5:  # After end time
        end_time_str = user_input
        try:
            # Extract event details from history
            event_name = [msg for role, msg in history if role == "User"][1]
            date_str = [msg for role, msg in history if role == "User"][2]
            start_time_str = [msg for role, msg in history if role == "User"][3]
            
            # Parse start and end times
            start_time = parse_date_time(date_str, start_time_str)
            end_time = parse_date_time(date_str, end_time_str)
            
            # Validate end time is after start time
            if end_time <= start_time:
                raise ValueError("End time must be after start time")

            # Create event
            try:
                service = authenticate_google()
                result = create_event(service, event_name, start_time, end_time)
                history.append(("Bot", result))
                history.append(("Bot", "Do you need to book any other appointments? (yes/no)"))
            except Exception as e:
                history.append(("Bot", f"Error: {str(e)}"))
        except ValueError as e:
            history.pop()
            history.append(("Bot", f"Invalid time: {str(e)}. Please enter a valid end time in HH:MM AM/PM format."))
    
    elif stage == 6:  # After yes/no
        if user_input.lower() == "yes":
            history.clear()
            history.append(("Bot", "Hi! How may I assist you?"))
        elif user_input.lower() == "no":
            history.append(("Bot", "Thank you! Have a nice day."))
        else:
            history.pop()
            history.append(("Bot", "Please answer with 'yes' or 'no'."))

    return history

def display_chat(history):
    """Display chat messages."""
    chat_display = []
    for role, message in history:
        if role == "User":
            chat_display.append([message, None])
        else:
            chat_display.append([None, message])
    return chat_display

# Create Gradio interface
with gr.Blocks() as iface:
    gr.Markdown("""
    <h1>Google Calendar Appointment Bot</h1>
    <p>Type 'restart' at any time to start over.</p>
    """)
    chatbot = gr.Chatbot()
    user_input = gr.Textbox(placeholder="Type your response here...")
    send_button = gr.Button("Send")
    restart_button = gr.Button("Restart Conversation")

    def reset_conversation():
        history = [("Bot", "Hi! How may I assist you?")]
        return display_chat(history), history

    def handle_input(user_input, history):
        if not user_input.strip():
            return display_chat(history), history, ""
        history = conversational_flow(history, user_input)
        return display_chat(history), history, ""

    history_state = gr.State([])
    send_button.click(handle_input, inputs=[user_input, history_state], outputs=[chatbot, history_state, user_input])
    user_input.submit(handle_input, inputs=[user_input, history_state], outputs=[chatbot, history_state, user_input])
    restart_button.click(reset_conversation, outputs=[chatbot, history_state])
    iface.load(reset_conversation, outputs=[chatbot, history_state])

if __name__ == "__main__":
    iface.launch()