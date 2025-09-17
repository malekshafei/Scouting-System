import requests
from bs4 import BeautifulSoup
import re
import time

class TransfermarktScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Position mapping - customize as needed
        self.position_mapping = {
            'Goalkeeper': '1',
            'Defender - Centre-Back': '4',
            'Defender - Left-Back': '3', 
            'Defender - Right-Back': '2',
            'Midfield - Defensive Midfield': '6',
            'Midfield - Central Midfield': '8',
            'Midfield - Attacking Midfield': '10',
            'Midfield - Left Midfield': '11',
            'Midfield - Right Midfield': '7',
            'Attack - Left Winger': '11',
            'Attack - Right Winger': '7',
            'Attack - Second Striker': '9',
            'Attack - Centre-Forward': '9',
        }

    def _format_league_level(self, league_level_text):
        """Convert league level to Country-Number format"""
        if not league_level_text or league_level_text == 'N/A':
            return 'NA'
         
        # Split by " - " to get country and tier
        if ' - ' in league_level_text:
            country, tier = league_level_text.split(' - ', 1)
            tier_lower = tier.lower()
            
            if 'first tier' in tier_lower:
                return f"{country}1"
            elif 'second tier' in tier_lower:
                return f"{country}2"
            elif 'third tier' in tier_lower:
                return f"{country}3"
            elif 'youth league' in tier_lower:
                return f"{country}YL"
            else:
                return 'NA'
        
        return 'NA'
    
    def _format_date_of_birth(self, dob):
        """Convert DD.MM.YYYY to MM/YY format"""
        if not dob or dob == 'N/A':
            return 'N/A'
        
        # Match DD.MM.YYYY pattern
        date_match = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', dob)
        if date_match:
            day, month, year = date_match.groups()
            # Convert to MM/YY format
            return f"{month.zfill(2)}/{year[-2:]}"
        
        return 'N/A'
    
    def _format_height(self, height):
        """Convert height like '1,82 m' to '182'"""
        if not height or height == 'N/A':
            return 'N/A'
        
        # Extract numbers from height string
        height_match = re.search(r'(\d+)[,.]?(\d*)', height)
        if height_match:
            whole_part = height_match.group(1)
            decimal_part = height_match.group(2) or '0'
            
            # Convert to cm format
            if len(whole_part) == 1:  # Format like "1,82 m"
                return f"{whole_part}{decimal_part.ljust(2, '0')}"
            else:  # Format like "182 cm"
                return whole_part
        
        return 'N/A'
    
    def _format_foot(self, foot):
        """Capitalize first letter of foot"""
        if not foot or foot == 'N/A':
            return 'N/A'
        
        return foot.capitalize()
    
    def _format_position(self, position):
        """Map position using position_mapping"""
        if not position or position == 'N/A':
            return 'N/A'
        
        # Try to find exact match first
        if position in self.position_mapping:
            return self.position_mapping[position]
        
        # Try partial matching for complex positions like "Defender - Centre-Back"
        for key, value in self.position_mapping.items():
            if key.lower() in position.lower():
                return value
        
        # If no mapping found, return original
        return position
    
    def _format_market_value(self, market_value):
        """Convert market value to float format (e.g., €6.00m -> 6.0, €500k -> 0.5)"""
        if not market_value or market_value == 'N/A':
            return 'N/A'
        
        # Remove spaces and extract the numeric part
        cleaned = market_value.replace(' ', '').lower()
        
        # Match pattern like €6.00m, €500k, €1.5b
        mv_match = re.search(r'€?([\d.,]+)([kmb])?', cleaned)
        if mv_match:
            number_str = mv_match.group(1).replace(',', '.')
            unit = mv_match.group(2) if mv_match.group(2) else ''
            
            try:
                number = float(number_str)
                
                if unit == 'k':
                    return round(number / 1000, 2)  # Convert k to millions
                elif unit == 'm' or unit == '':
                    return round(number, 1)
                elif unit == 'b':
                    return round(number * 1000, 1)  # Convert billions to millions
                else:
                    return round(number, 1)
                    
            except ValueError:
                return 'N/A'
        
        return 'N/A'
    
    def scrape_player_info(self, url):
        """
        Scrape player information from Transfermarkt using the actual HTML structure
        """
        try:
            time.sleep(2)
            
            response = self.session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            player_info = {}
            
            # === FROM HEADER SECTION (Image 1) ===
            
            # Player Name - from h1 with class "data-header__headline-wrapper"
            name_elem = soup.select_one('h1.data-header__headline-wrapper')
            if name_elem:
                # Get all text nodes, preserving spaces between elements
                name_parts = []
                for element in name_elem.descendants:
                    if element.name is None:  # Text node
                        text = element.strip()
                        if text and not re.match(r'^#\d+$', text):  # Exclude shirt numbers
                            name_parts.append(text)
                
                if name_parts:
                    player_info['Player Name'] = ' '.join(name_parts)
                else:
                    # Fallback method
                    name_text = name_elem.get_text(separator=' ', strip=True)
                    name_clean = re.sub(r'#\d+', '', name_text).strip()
                    player_info['Player Name'] = re.sub(r'\s+', ' ', name_clean)
            else:
                player_info['Player Name'] = 'N/A'
            
            # Player ID - from tm-watchlist element or URL
            watchlist_elem = soup.select_one('tm-watchlist[player-id]')
            if watchlist_elem:
                player_info['Player ID'] = watchlist_elem.get('player-id')
            else:
                # Extract from URL as fallback
                id_match = re.search(r'/spieler/(\d+)', url)
                player_info['Player ID'] = id_match.group(1) if id_match else 'N/A'
            
            # Club - from data-header__club span
            club_elem = soup.select_one('span.data-header__club a')
            if club_elem:
                player_info['Club'] = club_elem.get_text(strip=True)
            else:
                player_info['Club'] = 'N/A'
            
            # League - from data-header__league-link
            league_elem = soup.select_one('a.data-header__league-link')
            if league_elem:
                player_info['League'] = league_elem.get_text(strip=True)
            else:
                player_info['League'] = 'N/A'
            
            # League Level/Country - from data-header section 
            # Looking for the span.data-header__content that contains league level info
            league_level_content = soup.select_one('span.data-header__label + span.data-header__content')
            if league_level_content:
                # Get country from flag image
                country_img = league_level_content.find('img')
                country = ''
                if country_img:
                    country = country_img.get('title') or country_img.get('alt', '')
                
                # Get league level text (like "Second Tier")
                level_text = league_level_content.get_text(strip=True)
                
                # Format as "Country - Level" 
                if country and level_text:
                    player_info['League Level'] = f"{country} - {level_text}"
                elif level_text:
                    player_info['League Level'] = level_text
                elif country:
                    player_info['League Level'] = country
                else:
                    player_info['League Level'] = 'N/A'
            else:
                # Alternative: look for any data-header__content that might contain league info
                all_content_spans = soup.select('span.data-header__content')
                for content_span in all_content_spans:
                    # Check if this span contains flag image and text
                    country_img = content_span.find('img')
                    if country_img and content_span.get_text(strip=True):
                        country = country_img.get('title') or country_img.get('alt', '')
                        level_text = content_span.get_text(strip=True)
                        if country and level_text:
                            player_info['League Level'] = f"{country} - {level_text}"
                            break
                else:
                    player_info['League Level'] = 'N/A'
            
            # === FROM PLAYER DATA SECTION (Image 2) ===
            
            # Initialize player data fields
            player_data_fields = {
                'Date of Birth': 'N/A',
                'Age': 'N/A',
                'Height': 'N/A',
                'Position': 'N/A',
                'Foot': 'N/A',
                'Player Agent': 'N/A',
                'Contract Expires': 'N/A',
                'Market Value': 'N/A'
            }
            
            # Find all info-table spans - they come in pairs (label + content)
            info_spans = soup.select('span.info-table__content')
            
            # Also try to find date of birth more specifically
            dob_found = False
            
            # Method 1: Look for date of birth in info table
            for span in info_spans:
                span_text = span.get_text(strip=True).lower()
                
                # Get the next bold span which contains the value
                next_bold = span.find_next_sibling('span', class_='info-table__content--bold')
                if not next_bold:
                    continue
                
                value = next_bold.get_text(strip=True)
                
                # Match fields based on content
                if 'name in home country' in span_text:
                    continue  # Skip this field
                elif 'date of birth' in span_text:
                    # Extract date and age from the link/text
                    date_link = next_bold.find('a')
                    if date_link:
                        date_text = date_link.get_text(strip=True)
                        # Parse "19.10.1996 (28)" format
                        date_match = re.search(r'([\d.]+)\s*\((\d+)\)', date_text)
                        if date_match:
                            player_data_fields['Date of Birth'] = date_match.group(1)
                            player_data_fields['Age'] = date_match.group(2)
                            dob_found = True
                        else:
                            player_data_fields['Date of Birth'] = date_text
                            dob_found = True
                    else:
                        # Sometimes the date is directly in the span without a link
                        date_match = re.search(r'([\d.]+)\s*\((\d+)\)', value)
                        if date_match:
                            player_data_fields['Date of Birth'] = date_match.group(1)
                            player_data_fields['Age'] = date_match.group(2)
                            dob_found = True
                elif 'age' in span_text and not dob_found:
                    # Sometimes age and DOB are in separate fields
                    age_match = re.search(r'(\d+)', value)
                    if age_match:
                        player_data_fields['Age'] = age_match.group(1)
                elif 'height' in span_text:
                    player_data_fields['Height'] = value
                elif 'position' in span_text:
                    player_data_fields['Position'] = value
                elif 'foot' in span_text:
                    player_data_fields['Foot'] = value
                elif 'player agent' in span_text or 'agent' in span_text:
                    player_data_fields['Player Agent'] = value
                elif 'contract expires' in span_text or ('contract' in span_text and 'until' in span_text):
                    player_data_fields['Contract Expires'] = value
            
            # Method 2: Alternative search for date of birth if not found
            if not dob_found:
                # Look for any link that contains a date pattern
                date_links = soup.find_all('a', href=re.compile(r'/aktuell/waspassiertheute/'))
                for link in date_links:
                    link_text = link.get_text(strip=True)
                    date_match = re.search(r'([\d.]+)\s*\((\d+)\)', link_text)
                    if date_match:
                        player_data_fields['Date of Birth'] = date_match.group(1)
                        player_data_fields['Age'] = date_match.group(2)
                        break
            
            # Alternative method for contract expiry - look for specific date patterns
            if player_data_fields['Contract Expires'] == 'N/A':
                date_pattern = r'\b\d{2}\.\d{2}\.\d{4}\b'
                all_dates = []
                for span in soup.select('span.info-table__content--bold'):
                    text = span.get_text(strip=True)
                    if re.match(date_pattern, text):
                        all_dates.append(text)
                
                # Usually contract expiry is the last/latest date
                if all_dates:
                    # Sort dates and take the latest one (assuming it's contract expiry)
                    sorted_dates = sorted(all_dates, key=lambda x: x.split('.')[::-1])
                    player_data_fields['Contract Expires'] = sorted_dates[-1]
            
            # === MARKET VALUE EXTRACTION ===
            
            # Look for market value in the specific structure shown
            market_value_elem = soup.select_one('a.data-header__market-value-wrapper')
            if market_value_elem:
                # Get the text content and extract the value
                mv_text = market_value_elem.get_text(strip=True)
                player_data_fields['Market Value'] = mv_text
            else:
                # Alternative method: look for the specific span structure
                waehrung_spans = soup.select('span.waehrung')
                if len(waehrung_spans) >= 2:
                    # Find the parent element and get full text
                    parent_elem = waehrung_spans[0].parent
                    if parent_elem:
                        full_text = parent_elem.get_text(strip=True)
                        # Extract the pattern like "€6.00m"
                        mv_match = re.search(r'€[\d.,]+[kmb]?', full_text)
                        if mv_match:
                            player_data_fields['Market Value'] = mv_match.group()
                        else:
                            player_data_fields['Market Value'] = full_text
                else:
                    player_data_fields['Market Value'] = 'N/A'
            
            # Combine all data
            player_info.update(player_data_fields)
            
            # Apply formatting transformations
            player_info['League Level'] = self._format_league_level(player_info.get('League Level'))
            player_info['Date of Birth'] = self._format_date_of_birth(player_info.get('Date of Birth'))
            player_info['Height'] = self._format_height(player_info.get('Height'))
            player_info['Foot'] = self._format_foot(player_info.get('Foot'))
            player_info['Position'] = self._format_position(player_info.get('Position'))
            player_info['Market Value'] = self._format_market_value(player_info.get('Market Value'))
            
            return player_info
            
        except requests.RequestException as e:
            print(f"Network error: {e}")
            return None
        except Exception as e:
            print(f"Parsing error: {e}")
            return None
    
    def save_to_csv(self, player_data_list, filename='transfermarkt_players.csv'):
        """Save player data to CSV file"""
        try:
            import pandas as pd
            
            df = pd.DataFrame(player_data_list)
            df.to_csv(filename, index=False)
            print(f"Data saved to {filename}")
            return True
        except ImportError:
            print("pandas not installed. Saving as basic CSV...")
            import csv
            
            if player_data_list:
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = player_data_list[0].keys()
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(player_data_list)
                print(f"Data saved to {filename}")
                return True
            return False

def main():
    """Example usage"""
    scraper = TransfermarktScraper()
    
    # Test URLs
    test_urls = [
        "https://www.transfermarkt.com/jeremiah-st-juste/profil/spieler/288253",
        # Add more URLs here for batch processing
    ]
    
    # Single player
    print("=== SINGLE PLAYER TEST ===")
    player_data = scraper.scrape_player_info(test_urls[0])
    
    if player_data:
        print("\n=== PLAYER INFORMATION ===")
        for key, value in player_data.items():
            print(f"{key}: {value}")
    else:
        print("Failed to scrape player information")

if __name__ == "__main__":
    main()

# ===== EASY-TO-USE FUNCTIONS FOR OTHER PROGRAMS =====

def get_player_data(tm_link):
    """
    Simple function to get player data from a Transfermarkt link
    
    Args:
        tm_link (str): Transfermarkt player profile URL
        
    Returns:
        dict: Player information or None if failed
    """
    scraper = TransfermarktScraper()
    print(tm_link)
    return scraper.scrape_player_info(tm_link)


# ===== USAGE EXAMPLES =====
