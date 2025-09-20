import streamlit as st
import pandas as pd
import re
import zipfile
import io
from pathlib import Path
from typing import Dict, Set
import base64

# Set page config
st.set_page_config(
    page_title="CSV Cleaner Tool",
    page_icon="🧹",
    layout="wide"
)

class OptimizedCSVCleaner:
    def __init__(self):
        """Initialize the CSV cleaner with cleaning rules."""
        
        # Header mappings - only keep what gets mapped
        self.header_mappings = {
            "Badge": "BADGE", "First Name": "FIRSTNAME", "Middle Name": "MIDDLENAME",
            "Last Name": "LASTNAME", "Date Of Birth": "BDAY", "Age": "AGE",
            "Home Facility": "LOCATION", "Email": "EMAIL", "Do Not Mail": "DO_NOT_MAIL",
            "Mobile Phone": "SMS", "Line Address": "ADDRESS", "City": "CITY",
            "State": "STATE", "Postal": "ZIP", "Country": "COUNTRY",
            "Last Visit Date": "LAST_VISIT", "Participant Agreement": "PARTICIPANT_AGREEMENT",
            "Belay": "BELAY_CERTIFIED", "Climbing Experience": "EXPERIENCE_LEVEL",
            "Referred By": "REFERRED_BY", "How Did You Hear About Us": "HOW_DID_YOU_HEAR",
            "Gender": "GENDER", "Pronouns": "PRONOUN", "Outdoor Aor": "OUTDOOR_AOR",
            "Eligible For S1": "ELIGIBLE_S1", "Customer Id": "CUSTOMER_ID"
        }
        
        # Cell value mappings
        self.cell_mappings = {
            "BADGE": {"Staff": "STAFF", "Member": "MEMBER", "Member (frz)": "FROZEN",
                     "30-Day Member": "PREPAID-30", "Day Pass Pack": "MULTI_PASS"},
            "LOCATION": {"Alexandria": "ALX", "Sterling": "STR", "Rio": "RIO"}
        }
        
        # Interest field mappings
        self.interest_keywords = {
            "Adult Climbing Programs": "INTEREST_ADULT",
            "Fitness + Yoga": "INTEREST_FITNESS",
            "Youth Climbing Programs": "INTEREST_YOUTH", 
            "Outdoor Climbing Programs (SR Climbing Guides)": "INTEREST_OUTDOOR"
        }
        
        # Date fields that need formatting
        self.date_fields = ["BDAY", "LAST_VISIT"]
        
        # Final valid columns
        self.valid_columns = (set(self.header_mappings.values()) | 
                            {"INTEREST_YOUTH", "INTEREST_ADULT", "INTEREST_OUTDOOR", "INTEREST_FITNESS"})

    def clean_phone(self, phone: str) -> str:
        """Clean phone number - keep digits only."""
        return re.sub(r'\D', '', str(phone)) if pd.notna(phone) and phone else ""

    def format_date(self, date_str: str, age: str = None) -> str:
        """Format date to MM-DD-YYYY format, using age to infer century for 2-digit years."""
        if pd.isna(date_str) or not date_str or str(date_str).strip() == "":
            return ""
        
        try:
            date_str = str(date_str).strip()
            date_obj = None
            
            date_formats = [
                "%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", 
                "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y", "%m.%d.%Y",
            ]
            
            for fmt in date_formats:
                try:
                    date_obj = pd.to_datetime(date_str, format=fmt)
                    break
                except (ValueError, TypeError):
                    continue
            
            if date_obj is None:
                two_digit_formats = ["%m/%d/%y", "%m-%d-%y", "%m.%d.%y"]
                
                for fmt in two_digit_formats:
                    try:
                        temp_date = pd.to_datetime(date_str, format=fmt)
                        year = temp_date.year
                        month = temp_date.month
                        day = temp_date.day
                        
                        if age and str(age).strip() and str(age).strip().isdigit():
                            age_num = int(str(age).strip())
                            current_year = pd.Timestamp.now().year
                            birth_year_estimate = current_year - age_num
                            
                            if year < 50:
                                if birth_year_estimate >= 2000:
                                    year = 2000 + (year - 2000)
                                else:
                                    year = 1900 + year
                            else:
                                year = 1900 + (year - 1900)
                        else:
                            if year < 50:
                                year = 2000 + year
                        
                        date_obj = pd.Timestamp(year=year, month=month, day=day)
                        break
                        
                    except (ValueError, TypeError):
                        continue
            
            if date_obj is None:
                date_obj = pd.to_datetime(date_str, errors='coerce')
            
            if pd.notna(date_obj):
                return date_obj.strftime("%m-%d-%Y")
            else:
                return str(date_str)
                
        except Exception as e:
            return str(date_str)

    def process_interests(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process interest fields into separate boolean columns."""
        for col in ["INTEREST_YOUTH", "INTEREST_ADULT", "INTEREST_OUTDOOR", "INTEREST_FITNESS"]:
            df[col] = ""
        
        interest_col = None
        if 'Interest' in df.columns:
            interest_col = 'Interest'
        elif 'interest' in df.columns:
            interest_col = 'interest'
            
        if interest_col:
            matches_found = 0
            for idx, value in df[interest_col].items():
                if pd.notna(value) and value:
                    value_str = str(value).strip()
                    if value_str:
                        for keyword, col_name in self.interest_keywords.items():
                            if keyword.lower() in value_str.lower():
                                df.loc[idx, col_name] = "YES"
                                matches_found += 1
            
            st.write(f"📊 Found {matches_found} interest matches")
            df.drop(interest_col, axis=1, inplace=True)
        
        if 'Youth Programs Interest' in df.columns:
            mask = df['Youth Programs Interest'].str.lower() == 'yes'
            df.loc[mask, 'INTEREST_YOUTH'] = "YES"
            df.drop('Youth Programs Interest', axis=1, inplace=True)
        
        return df

    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean the entire dataframe efficiently."""
        cleaned = df.copy()
        
        # Show progress
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("🔄 Renaming headers...")
        cleaned.rename(columns=self.header_mappings, inplace=True)
        progress_bar.progress(20)
        
        status_text.text("🔄 Processing interest fields...")
        cleaned = self.process_interests(cleaned)
        progress_bar.progress(40)
        
        status_text.text("🔄 Applying cell mappings...")
        for col, mappings in self.cell_mappings.items():
            if col in cleaned.columns:
                if col == "BADGE":
                    cleaned[col] = cleaned[col].fillna("").replace("", "GUEST")
                cleaned[col] = cleaned[col].map(mappings).fillna(cleaned[col])
        progress_bar.progress(60)
        
        status_text.text("🔄 Cleaning phone numbers...")
        if 'SMS' in cleaned.columns:
            cleaned['SMS'] = cleaned['SMS'].apply(self.clean_phone)
        progress_bar.progress(80)
        
        status_text.text("🔄 Formatting dates...")
        for date_field in self.date_fields:
            if date_field in cleaned.columns:
                if date_field == "BDAY" and "AGE" in cleaned.columns:
                    cleaned[date_field] = cleaned.apply(
                        lambda row: self.format_date(row[date_field], row.get("AGE")), axis=1
                    )
                else:
                    cleaned[date_field] = cleaned[date_field].apply(self.format_date)
        
        status_text.text("🔄 Filtering final columns...")
        final_cols = [col for col in cleaned.columns if col in self.valid_columns]
        cleaned = cleaned[final_cols]
        
        progress_bar.progress(100)
        status_text.text("✅ Processing complete!")
        
        return cleaned


def create_download_link(df, filename):
    """Create a download link for a dataframe."""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">📥 Download {filename}</a>'
    return href

def create_zip_download(files_dict):
    """Create a zip file download with multiple CSVs."""
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, df in files_dict.items():
            csv_data = df.to_csv(index=False)
            zip_file.writestr(filename, csv_data)
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

def main():
    # Title and description
    st.title("🧹 CSV Cleaner Tool")
    st.markdown("""
    Upload your CSV files to clean and standardize the data according to your business rules.
    
    **What this tool does:**
    - Standardizes column headers
    - Cleans phone numbers (digits only)
    - Formats dates to MM-DD-YYYY
    - Processes interest fields into separate columns
    - Maps facility names (Alexandria→ALX, Sterling→STR, Rio→RIO)
    - Maps badge types (Member→MEMBER, Staff→STAFF, etc.)
    """)
    
    # Initialize cleaner
    if 'cleaner' not in st.session_state:
        st.session_state.cleaner = OptimizedCSVCleaner()
    
    cleaner = st.session_state.cleaner
    
    # Sidebar for settings
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Show mapping rules
        with st.expander("📋 Header Mappings"):
            for old, new in cleaner.header_mappings.items():
                st.text(f"{old} → {new}")
        
        with st.expander("🏢 Facility Mappings"):
            for old, new in cleaner.cell_mappings["LOCATION"].items():
                st.text(f"{old} → {new}")
        
        with st.expander("🎫 Badge Mappings"):
            for old, new in cleaner.cell_mappings["BADGE"].items():
                st.text(f"{old} → {new}")
    
    # File upload section
    st.header("📁 Upload CSV Files")
    
    uploaded_files = st.file_uploader(
        "Choose CSV files",
        accept_multiple_files=True,
        type=['csv'],
        help="You can upload multiple CSV files at once"
    )
    
    if uploaded_files:
        st.success(f"Uploaded {len(uploaded_files)} file(s)")
        
        # Process files
        if st.button("🚀 Clean All Files", type="primary"):
            cleaned_files = {}
            
            for uploaded_file in uploaded_files:
                st.subheader(f"Processing: {uploaded_file.name}")
                
                try:
                    # Read the CSV
                    df = pd.read_csv(uploaded_file)
                    st.write(f"📊 **Input:** {df.shape[0]} rows, {df.shape[1]} columns")
                    
                    # Show original columns
                    with st.expander(f"Original columns in {uploaded_file.name}"):
                        st.write(list(df.columns))
                    
                    # Clean the dataframe
                    cleaned_df = cleaner.clean_dataframe(df)
                    st.write(f"📈 **Output:** {cleaned_df.shape[0]} rows, {cleaned_df.shape[1]} columns")
                    
                    # Show cleaned columns
                    with st.expander(f"Cleaned columns in {uploaded_file.name}"):
                        st.write(list(cleaned_df.columns))
                    
                    # Preview cleaned data
                    with st.expander(f"Preview cleaned data from {uploaded_file.name}"):
                        st.dataframe(cleaned_df.head(10))
                    
                    # Store for download
                    clean_filename = f"clean_{uploaded_file.name}"
                    cleaned_files[clean_filename] = cleaned_df
                    
                    # Individual download link
                    st.markdown(
                        create_download_link(cleaned_df, clean_filename), 
                        unsafe_allow_html=True
                    )
                    
                    st.success(f"✅ Successfully processed {uploaded_file.name}")
                    
                except Exception as e:
                    st.error(f"❌ Error processing {uploaded_file.name}: {str(e)}")
                
                st.divider()
            
            # Bulk download if multiple files
            if len(cleaned_files) > 1:
                st.header("📦 Bulk Download")
                
                zip_data = create_zip_download(cleaned_files)
                
                st.download_button(
                    label="📥 Download All Cleaned Files (ZIP)",
                    data=zip_data,
                    file_name="cleaned_csv_files.zip",
                    mime="application/zip",
                    type="primary"
                )
    
    # Instructions
    st.header("📖 How to Use")
    st.markdown("""
    1. **Upload Files:** Click "Browse files" or drag & drop CSV files
    2. **Process:** Click "Clean All Files" to start processing
    3. **Download:** Use individual download links or bulk ZIP download
    4. **Review:** Check the preview tables to verify the cleaning worked correctly
    
    **Tips:**
    - You can upload multiple files at once
    - The tool will show progress for each file
    - Check the "Settings" sidebar to see what transformations are applied
    - If processing fails, check that your CSV has the expected column names
    """)

if __name__ == "__main__":
    main()
