# FoodShare AI Viva Questions and Answers

> This file was written for the earlier prototype stage. For current Flask, SQLite, matching, and experiment answers, use [FACULTY_VIVA.md](FACULTY_VIVA.md).

Answers refer to the source currently in this workspace. Backend-related answers clearly describe future work rather than claiming it exists.

1. **Why did you select this project?**  
   We selected the idea because food sharing and food waste are relatable community concerns. The current work presents a website prototype for that idea.

2. **What problem does FoodShare AI aim to address?**  
   It aims to make surplus food easier to discover and share. The current prototype explains the concept but does not process real donations.

3. **How can food sharing reduce waste?**  
   If safe surplus food reaches someone who can use it, less edible food may be discarded. This is the intended outcome, not a measured result from this prototype.

4. **What is the current implementation?**  
    It has a static single-page frontend made from HTML, CSS, and JavaScript, plus a standalone Python matching experiment.

5. **What does HTML do in this project?**  
   HTML defines the page sections, text, links, sample listing cards, and accessibility labels.

6. **What does CSS do?**  
   CSS defines the colors, typography, spacing, visual states, and responsive page layout.

7. **What does JavaScript do?**  
   It opens and closes the mobile navigation, handles Escape, and shows placeholder notices for matching and login.

8. **What is responsive design?**  
   Responsive design adapts a page layout to different screen widths. This stylesheet uses media queries for that purpose.

9. **What is a media query?**  
   It is a CSS rule that applies styles only under conditions such as a maximum viewport width.

10. **What is Flask?**  
    Flask is a Python web framework that can provide routes and APIs. It is not present in the current project files.

11. **What is an API?**  
    An API is a defined way for programs to exchange data. This frontend currently makes no API calls.

12. **What does HTTP GET usually do?**  
    GET is commonly used to retrieve information from a server. There is no GET endpoint in the current workspace.

13. **What does HTTP POST usually do?**  
    POST is commonly used to submit new data. There is no donation or request POST endpoint in the current workspace.

14. **What do PUT or PATCH commonly do?**  
    They commonly update existing data. No such update endpoint exists in the current source.

15. **What does HTTP DELETE commonly do?**  
    It requests removal of a resource. The current project has no backend resource or delete route.

16. **What is JSON?**  
    JSON is a text format often used to exchange structured data between a browser and an API. This project does not currently exchange JSON.

17. **What is SQLite?**  
    SQLite is a relational database stored in a file. No SQLite database or schema exists in this workspace.

18. **What is a primary key?**  
    A primary key uniquely identifies a row in a table. The project currently has no database tables.

19. **What is a foreign key?**  
    A foreign key links a row to a row in another table. No database relationships are implemented here.

20. **What is CRUD?**  
    CRUD means Create, Read, Update, and Delete. The static prototype does not perform CRUD operations on persisted data.

21. **How are donation records stored?**  
    They are not stored in the current version. The three listing cards are fixed HTML examples.

22. **Does the donation form validate user input?**  
    There is no donation form yet, so there is no donation validation. A future version should validate both in the browser and on the server.

23. **How does the frontend talk to Flask?**  
    It does not currently talk to Flask. A future integration could use JavaScript `fetch()` to call JSON endpoints.

24. **Does this project use AI or machine learning?**  
    There is no trained machine-learning model. A separate Python module does implement an explainable rule-based score and exhaustive allocation search, but the website does not use it yet.

25. **How would rule-based matching work in a future version?**  
    The standalone agent checks category, positive quantities and matching units, availability, request status, food safety, expiry, and urgency. It rejects invalid pairs before scoring and explains accepted pairs. It is not yet connected to website data.

26. **How are the impact statistics calculated?**  
    They are not calculated. They are fixed sample values in the HTML and are labeled as illustrative demo figures.

27. **Does the login link authenticate a user?**  
    No. It displays a placeholder notice. There is no registration, login, password storage, or session handling.

28. **What security does the current project have?**  
    It has no backend security features because no backend exists in this workspace. A future service would need authentication, authorization, validation, secure secret configuration, and safe database queries.

29. **What testing was performed?**  
    The page was opened in a browser, the menu and responsive layout were checked, and JavaScript syntax was checked. The Python agent has 20 passing tests and the synthetic comparison ran 25 repetitions per method.

30. **How can you run the current site?**  
    From the project root, run `python -m http.server 8000` and open `http://127.0.0.1:8000`. This runs a static file server, not Flask.

31. **Can the current site save data after a refresh?**  
    No. It has no database or data-submission code, so there is no saved donation data.

32. **What is one limitation of the current prototype?**  
    Its listings and statistics are illustrative static content, not real activity.

33. **What is a planned future improvement?**  
    Add a verified Flask API and SQLite schema, then connect real validated donation and request records to the matching agent while preserving the existing design.

34. **Why must server-side validation still be used if a form has browser validation?**  
    Browser checks can be bypassed. A server must independently validate submitted data before processing or storing it.

35. **What is a parameterized SQL query?**  
    It separates SQL instructions from user values and helps prevent SQL injection. The current project has no SQL queries.

36. **Can you claim that this prototype has rescued a specific amount of food?**  
    No. Homepage figures are illustrative. The algorithm experiment reports synthetic allocation metrics only; it does not measure real food rescued.