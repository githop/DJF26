#!/usr/bin/env python3
"""
Generate a searchable HTML dashboard for flight information from the DJF26 database.
"""

import sqlite3
import re
import json
from datetime import datetime


# IATA (2-letter) to ICAO (3-letter) airline code mapping
IATA_TO_ICAO = {
    'UA': 'UAL',  # United Airlines
    'DL': 'DAL',  # Delta Air Lines
    'AS': 'ASA',  # Alaska Airlines
    'WN': 'SWA',  # Southwest Airlines
    'AA': 'AAL',  # American Airlines
    'B6': 'JBU',  # JetBlue
    'F9': 'FFT',  # Frontier Airlines
}


def extract_flight_number(details):
    """Extract flight number from details like 'arrive in Denver (UA 2660)'"""
    if not details:
        return None, None
    match = re.search(r'\(([A-Z]{2})\s*(\d+)\)', details)
    if match:
        iata_code = match.group(1)
        number = match.group(2)
        # Convert to ICAO code for FlightAware
        icao_code = IATA_TO_ICAO.get(iata_code, iata_code)
        flight_number_icao = f"{icao_code}{number}"
        flight_number_iata = f"{iata_code}{number}"
        return flight_number_iata, flight_number_icao
    return None, None


def extract_artist_names(artist_field, details):
    """Extract artist names from both fields"""
    names = []
    if artist_field and artist_field != '-':
        names.append(artist_field)
    return names


def determine_flight_type(details):
    """Determine if it's arrival or departure"""
    if not details:
        return 'Unknown'
    details_lower = details.lower()
    if 'arrive' in details_lower:
        return 'Arrival'
    elif 'depart' in details_lower:
        return 'Departure'
    return 'Unknown'


def format_date_sort_key(date_str):
    """Convert date string like '4/6 (Monday)' to sortable format"""
    try:
        # Extract month/day from format like "4/6 (Monday)"
        match = re.match(r'(\d+)/(\d+)', date_str)
        if match:
            month = int(match.group(1))
            day = int(match.group(2))
            # Assume 2026
            return f"2026-{month:02d}-{day:02d}"
    except:
        pass
    return date_str


def get_flight_data():
    """Fetch all flight data from the database"""
    conn = sqlite3.connect('db/master_schedule.db')
    cursor = conn.cursor()

    cursor.execute("""
        SELECT Date, Start, End, Activity, Details, Location, 
               "Location Address", "Location Destination", "Artist/Group", 
               Pax, Vehicles, Drivers, Notes
        FROM schedule 
        WHERE Activity = 'Flight'
        ORDER BY Date, Start
    """)

    flights = []
    for row in cursor.fetchall():
        (date, start, end, activity, details, location,
         location_addr, location_dest, artist_group, pax,
         vehicles, drivers, notes) = row

        flight_num_iata, flight_num_icao = extract_flight_number(details)
        flight_type = determine_flight_type(details)

        # Build FlightAware link if we have a flight number (use ICAO format)
        flightaware_link = None
        if flight_num_icao:
            # FlightAware URL format: https://flightaware.com/live/flight/UAL2660
            flightaware_link = f"https://flightaware.com/live/flight/{flight_num_icao}"

        flights.append({
            'date': date,
            'date_sort': format_date_sort_key(date),
            'time': start or 'TBD',
            'type': flight_type,
            'details': details or '',
            'artist_group': artist_group or '',
            'location': location or '',
            'address': location_addr or '',
            'flight_number': flight_num_iata,  # Display the IATA version (UA2643)
            'flight_number_icao': flight_num_icao,  # ICAO version for links
            'flightaware_link': flightaware_link,
            'drivers': drivers or '',
            'notes': notes or ''
        })

    conn.close()
    return flights


def generate_html(flights):
    """Generate the HTML dashboard"""

    # Group flights by date for the display
    flights_by_date = {}
    for flight in flights:
        date = flight['date']
        if date not in flights_by_date:
            flights_by_date[date] = []
        flights_by_date[date].append(flight)

    # Convert to JSON for JavaScript search
    flights_json = json.dumps(flights)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DJF26 Flight Dashboard</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
        }}

        header h1 {{
            color: #fff;
            font-size: 2.5rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}

        header p {{
            color: #aaa;
            font-size: 1.1rem;
        }}

        .stats-bar {{
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-bottom: 25px;
            flex-wrap: wrap;
        }}

        .stat-card {{
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            padding: 15px 25px;
            color: white;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.2);
        }}

        .stat-card .number {{
            font-size: 2rem;
            font-weight: bold;
            color: #ffd700;
        }}

        .stat-card .label {{
            font-size: 0.9rem;
            opacity: 0.8;
        }}

        .search-container {{
            margin-bottom: 15px;
            position: relative;
        }}

        .search-input {{
            width: 100%;
            max-width: 600px;
            margin: 0 auto;
            display: block;
            padding: 15px 25px;
            font-size: 1.1rem;
            border: none;
            border-radius: 50px;
            background: rgba(255,255,255,0.95);
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            transition: all 0.3s ease;
        }}

        .search-input:focus {{
            outline: none;
            box-shadow: 0 4px 25px rgba(255,215,0,0.3);
            transform: translateY(-2px);
        }}

        .search-input::placeholder {{
            color: #999;
        }}

        .sort-container {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 15px;
            margin-bottom: 25px;
            flex-wrap: wrap;
        }}

        .sort-select {{
            padding: 10px 20px;
            font-size: 1rem;
            border: none;
            border-radius: 25px;
            background: rgba(255,255,255,0.95);
            cursor: pointer;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}

        .sort-select:focus {{
            outline: none;
        }}

        .sort-direction-btn {{
            padding: 10px 20px;
            font-size: 1rem;
            border: none;
            border-radius: 25px;
            background: rgba(255,255,255,0.95);
            cursor: pointer;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: all 0.2s ease;
        }}

        .sort-direction-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(0,0,0,0.15);
        }}

        .sort-direction-btn:active {{
            transform: translateY(0);
        }}

        .flight-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
            gap: 20px;
        }}

        .flight-card {{
            background: white;
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            border-left: 5px solid #ddd;
        }}

        .flight-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 8px 30px rgba(0,0,0,0.2);
        }}

        .flight-card.arrival {{
            border-left-color: #28a745;
        }}

        .flight-card.departure {{
            border-left-color: #dc3545;
        }}

        .flight-card.train {{
            border-left-color: #6c757d;
        }}

        .flight-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            flex-wrap: wrap;
            gap: 10px;
        }}

        .flight-type-badge {{
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .flight-type-badge.arrival {{
            background: #d4edda;
            color: #155724;
        }}

        .flight-type-badge.departure {{
            background: #f8d7da;
            color: #721c24;
        }}

        .flight-type-badge.train {{
            background: #e2e3e5;
            color: #383d41;
        }}

        .flight-time {{
            font-size: 1.3rem;
            font-weight: bold;
            color: #333;
        }}

        .flight-date {{
            color: #666;
            font-size: 0.9rem;
            margin-bottom: 10px;
        }}

        .flight-details {{
            font-size: 1rem;
            line-height: 1.5;
            color: #444;
            margin-bottom: 12px;
        }}

        .flight-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #eee;
            font-size: 0.85rem;
            color: #666;
        }}

        .flight-meta span {{
            display: flex;
            align-items: center;
            gap: 5px;
        }}

        .flight-number {{
            display: inline-block;
            background: #f0f0f0;
            padding: 4px 10px;
            border-radius: 6px;
            font-family: monospace;
            font-weight: bold;
            color: #333;
            margin-top: 10px;
        }}

        .flightaware-btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            margin-top: 12px;
            padding: 10px 18px;
            background: linear-gradient(135deg, #ff6b6b, #ff8e53);
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 500;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px rgba(255,107,107,0.3);
        }}

        .flightaware-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(255,107,107,0.4);
        }}

        .flightaware-btn svg {{
            width: 16px;
            height: 16px;
        }}

        .no-results {{
            text-align: center;
            color: #fff;
            font-size: 1.2rem;
            margin-top: 50px;
            display: none;
        }}

        .highlight {{
            background: #fff3cd;
            padding: 2px 4px;
            border-radius: 3px;
        }}

        @media (max-width: 768px) {{
            .flight-grid {{
                grid-template-columns: 1fr;
            }}

            header h1 {{
                font-size: 1.8rem;
            }}

            .stats-bar {{
                gap: 15px;
            }}

            .stat-card {{
                padding: 10px 18px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>✈️ Denver Jazz Fest 2026</h1>
            <p>Flight Information Dashboard</p>
        </header>

        <div class="stats-bar">
            <div class="stat-card">
                <div class="number" id="total-flights">0</div>
                <div class="label">Total Flights</div>
            </div>
            <div class="stat-card">
                <div class="number" id="total-arrivals">0</div>
                <div class="label">Arrivals</div>
            </div>
            <div class="stat-card">
                <div class="number" id="total-departures">0</div>
                <div class="label">Departures</div>
            </div>
        </div>

        <div class="search-container">
            <input type="text" 
                   class="search-input" 
                   id="searchInput" 
                   placeholder="Search by artist, flight number, date, or location...">
        </div>

        <div class="sort-container">
            <select class="sort-select" id="sortSelect">
                <option value="datetime">Sort by Date & Time</option>
                <option value="artist">Sort by Artist Name</option>
                <option value="type">Sort by Flight Type</option>
                <option value="flight_number">Sort by Flight Number</option>
            </select>
            <button class="sort-direction-btn" id="sortDirectionBtn" title="Toggle sort direction">
                ↑ Ascending
            </button>
        </div>

        <div class="flight-grid" id="flightGrid">
            <!-- Flight cards will be inserted here -->
        </div>

        <div class="no-results" id="noResults">
            No flights found matching your search.
        </div>
    </div>

    <script>
        const flights = {flights_json};
        let currentSortField = 'datetime';
        let currentSortDirection = 'asc';
        let currentSearchTerm = '';

        function getFlightCardClass(type, details) {{
            if (details.toLowerCase().includes('train')) return 'train';
            if (type === 'Arrival') return 'arrival';
            if (type === 'Departure') return 'departure';
            return '';
        }}

        function getBadgeClass(type, details) {{
            if (details.toLowerCase().includes('train')) return 'train';
            if (type === 'Arrival') return 'arrival';
            if (type === 'Departure') return 'departure';
            return '';
        }}

        function sortFlights(flightsToSort, field, direction) {{
            const sorted = [...flightsToSort];
            
            sorted.sort((a, b) => {{
                let comparison = 0;
                
                switch(field) {{
                    case 'datetime':
                        // Sort by date_sort first, then by time
                        const dateA = a.date_sort || a.date;
                        const dateB = b.date_sort || b.date;
                        comparison = dateA.localeCompare(dateB);
                        if (comparison === 0) {{
                            // If same date, sort by time
                            const timeA = a.time || '00:00';
                            const timeB = b.time || '00:00';
                            comparison = timeA.localeCompare(timeB);
                        }}
                        break;
                    case 'artist':
                        const artistA = (a.artist_group || '').toLowerCase();
                        const artistB = (b.artist_group || '').toLowerCase();
                        comparison = artistA.localeCompare(artistB);
                        break;
                    case 'type':
                        const typeA = a.type || '';
                        const typeB = b.type || '';
                        comparison = typeA.localeCompare(typeB);
                        break;
                    case 'flight_number':
                        const numA = (a.flight_number || '').toLowerCase();
                        const numB = (b.flight_number || '').toLowerCase();
                        comparison = numA.localeCompare(numB);
                        break;
                }}
                
                return direction === 'asc' ? comparison : -comparison;
            }});
            
            return sorted;
        }}

        function renderFlights(flightsToRender, searchTerm = '') {{
            const grid = document.getElementById('flightGrid');
            const noResults = document.getElementById('noResults');

            if (flightsToRender.length === 0) {{
                grid.innerHTML = '';
                noResults.style.display = 'block';
                return;
            }}

            noResults.style.display = 'none';

            grid.innerHTML = flightsToRender.map(flight => {{
                const cardClass = getFlightCardClass(flight.type, flight.details);
                const badgeClass = getBadgeClass(flight.type, flight.details);
                
                // Highlight search terms
                let details = flight.details;
                let artist = flight.artist_group;
                let date = flight.date;
                let location = flight.location;
                
                if (searchTerm) {{
                    const regex = new RegExp(`(${{searchTerm}})`, 'gi');
                    details = details.replace(regex, '<span class="highlight">$1</span>');
                    artist = artist.replace(regex, '<span class="highlight">$1</span>');
                    date = date.replace(regex, '<span class="highlight">$1</span>');
                    location = location.replace(regex, '<span class="highlight">$1</span>');
                }}

                const flightAwareLink = flight.flightaware_link ? `
                    <a href="${{flight.flightaware_link}}" 
                       target="_blank" 
                       rel="noopener noreferrer"
                       class="flightaware-btn">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                            <path d="M2 17l10 5 10-5"/>
                            <path d="M2 12l10 5 10-5"/>
                        </svg>
                        Track on FlightAware
                    </a>
                ` : '';

                const flightNumberBadge = flight.flight_number ? 
                    `<span class="flight-number">${{flight.flight_number}}</span>` : '';

                const driverInfo = flight.drivers && flight.drivers !== '-' ? 
                    `<span>👤 ${{flight.drivers}}</span>` : '';

                return `
                    <div class="flight-card ${{cardClass}}">
                        <div class="flight-header">
                            <div>
                                <div class="flight-date">${{date}}</div>
                                <div class="flight-time">${{flight.time}}</div>
                            </div>
                            <span class="flight-type-badge ${{badgeClass}}">${{flight.type}}</span>
                        </div>
                        <div class="flight-details">${{details}}</div>
                        ${{flightNumberBadge}}
                        ${{flightAwareLink}}
                        <div class="flight-meta">
                            <span>📍 ${{location}}</span>
                            ${{driverInfo}}
                        </div>
                    </div>
                `;
            }}).join('');
        }}

        function getFilteredFlights() {{
            if (!currentSearchTerm) {{
                return flights;
            }}

            const term = currentSearchTerm.toLowerCase();
            return flights.filter(flight => {{
                return (
                    (flight.details && flight.details.toLowerCase().includes(term)) ||
                    (flight.artist_group && flight.artist_group.toLowerCase().includes(term)) ||
                    (flight.date && flight.date.toLowerCase().includes(term)) ||
                    (flight.location && flight.location.toLowerCase().includes(term)) ||
                    (flight.flight_number && flight.flight_number.toLowerCase().includes(term)) ||
                    (flight.drivers && flight.drivers.toLowerCase().includes(term))
                );
            }});
        }}

        function updateDisplay() {{
            let filtered = getFilteredFlights();
            let sorted = sortFlights(filtered, currentSortField, currentSortDirection);
            renderFlights(sorted, currentSearchTerm);
        }}

        function updateStats() {{
            const arrivals = flights.filter(f => f.type === 'Arrival').length;
            const departures = flights.filter(f => f.type === 'Departure').length;
            
            document.getElementById('total-flights').textContent = flights.length;
            document.getElementById('total-arrivals').textContent = arrivals;
            document.getElementById('total-departures').textContent = departures;
        }}

        function updateSortDirectionButton() {{
            const btn = document.getElementById('sortDirectionBtn');
            btn.textContent = currentSortDirection === 'asc' ? '↑ Ascending' : '↓ Descending';
        }}

        // Event listeners
        document.getElementById('searchInput').addEventListener('input', (e) => {{
            currentSearchTerm = e.target.value;
            updateDisplay();
        }});

        document.getElementById('sortSelect').addEventListener('change', (e) => {{
            currentSortField = e.target.value;
            updateDisplay();
        }});

        document.getElementById('sortDirectionBtn').addEventListener('click', () => {{
            currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
            updateSortDirectionButton();
            updateDisplay();
        }});

        // Initialize
        updateStats();
        updateSortDirectionButton();
        updateDisplay();
    </script>
</body>
</html>
'''

    return html


def main():
    """Main function to generate the dashboard"""
    print("Fetching flight data from database...")
    flights = get_flight_data()
    print(f"Found {len(flights)} flights")

    print("Generating HTML dashboard...")
    html = generate_html(flights)

    output_file = 'flight_dashboard.html'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Dashboard created: {output_file}")
    print(f"Open this file in your browser to view the dashboard")


if __name__ == '__main__':
    main()
