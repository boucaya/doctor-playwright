# Doctor Availability Checker

This project is designed to check the availability of doctors using Playwright for web automation. It retrieves available appointment slots and can send notifications when slots are found.

## Project Structure

```
doctor-playwright
├── src
│   ├── checker.py        # Main logic for checking doctor availability
│   ├── browser.py        # Manages the Playwright browser instance
│   └── __init__.py       # Marks the src directory as a Python package
├── tests
│   └── test_checker.py    # Unit tests for the availability checking logic
├── requirements.txt       # Lists project dependencies
├── pyproject.toml         # Project configuration and metadata
├── .gitignore             # Specifies files to ignore in Git
└── README.md              # Documentation for the project
```

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd doctor-playwright
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers:**
   ```bash
   playwright install
   ```

## Usage

To check doctor availability, run the following command:

```bash
python src/checker.py
```

Make sure to configure the necessary parameters in `checker.py` before running the script.

## Running Tests

To run the tests, use the following command:

```bash
pytest tests/test_checker.py
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.