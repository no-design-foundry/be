# No Design Foundry – Backend

Welcome to the source code repository for the backend of [nodesignfoundry.com](https://www.nodesignfoundry.com).

## Setup Instructions

1. **Install Dependencies**:
    - It is recommended to use a virtual environment, such as `venv`, to manage dependencies.
    - To install all required packages, run:
      ```sh
      python -m pip install -r requirements.txt
      ```

1. **Optional: Develop Font Filters (If you wish to develop font filters)**:
    - Install dependencies 
      ```sh
      python -m pip install -r requirements-dev.txt
      ```
    - clone the filters repository from GitHub:
      [github.com/no-design-foundry](https://github.com/no-design-foundry).
    - Place the cloned repository in a directory adjacent to the project root.
    - Install the filters using the following command (example shown for `filters-rotorizer`):
      ```sh
      python -m pip install -e ../filters-rotorizer
      ```
1. **Running the server**:
    - For development 
      ```sh
      python app.py
      ```
    - For production preview
      ```sh
      gunicorn app:app --bind=127.0.0.1:8000   
      ```

1. **Running tests**
  - run `pytest` in this folder

1. Have fun 😇
