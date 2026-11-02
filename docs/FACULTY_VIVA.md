# FoodShare AI: Likely Faculty Viva Questions

1. **What problem does the project address?**  
   It supports sharing safe surplus food with people who request it. The software checks matching rules and prevents invalid allocation.

2. **Is this a machine-learning model?**  
   No. It is a rule-based scoring algorithm and an exhaustive search for small allocation datasets. It does not train or learn weights.

3. **What are the algorithm's inputs?**  
   Donation ID, category, quantity, unit, status, safety declaration, expiry, and optional location; plus request ID, category, quantity, unit, status, urgency, and optional location.

4. **What happens before scoring?**  
   The agent rejects pairs with missing data, incompatible category/unit, insufficient stock, closed/unavailable status, unsafe food, or invalid/past expiry.

5. **What does the score mean?**  
   It is a 0-100 compatibility ranking made from category (40), quantity fit (up to 25), urgency (5/12/20), and location (15 same named area, 5 different known areas, 0 missing). It is not a probability.

6. **What is the greedy baseline?**  
   It repeatedly takes the currently highest-scoring feasible pair. It is simple and relatively quick but can make a local choice that blocks a better total allocation.

7. **What does exhaustive search do?**  
   For each request it tries each feasible donation and the option to leave it unmatched, tracking remaining stock. It chooses the allocation satisfying the most requests, then the highest total score.

8. **Why not use exhaustive search for every real application?**  
   Its choices grow exponentially with request count. It is understandable and practical for our small experiment, but large datasets need pruning or a scalable optimization method.

9. **How does the app stop double allocation?**  
   Acceptance starts a SQLite write transaction, checks eligibility again, inserts a unique allocation, completes the request, and reduces remaining donation quantity. Database constraints and the transaction reject repeated allocation.

10. **What do the experiment results show?**  
    On the fixed synthetic dataset, greedy fulfilled five requests and 16 units; exhaustive search fulfilled six requests and 24 units. Both had zero invalid allocations. Search was slower. This is one synthetic test, not proof that it is always better.

11. **How does JavaScript communicate with Flask?**  
    The page uses `fetch()` with JSON. Flask validates the request, uses parameterized SQLite queries, and returns JSON and HTTP status codes.

12. **How are passwords handled?**  
    Werkzeug password hashing is used; the database stores the hash, not the submitted password. The app also uses session cookies and CSRF headers for mutations.

13. **How are administrator permissions assigned?**  
    The server compares registered email against the `FOODSHARE_ADMIN_EMAILS` environment allowlist. Clients cannot choose the admin role directly. The setting must be protected.

14. **How are the dashboard quantities counted?**  
    Donation/request counts use database rows. Allocated quantities are grouped by unit, since kilograms and loaves must not be added together. They are not verified climate or environmental impact.

15. **What is synthetic in this project?**  
    Experiment CSV inputs and allocation comparisons are synthetic. The live demonstration workflow uses its own SQLite records. Synthetic results are never shown as real listings.

16. **What are the main limitations?**  
    Category and unit matching are exact, no unit conversions or partial fulfillment exist, locations are text areas rather than distances, safety is self-declared, and exhaustive search is only for small datasets.

17. **How can the project be tested?**  
    Run `python -m pytest -q` for unit/API tests and `python run_experiments.py` for the synthetic comparison and charts.

18. **How is the database initialized?**  
    Flask creates the `instance/foodshare.sqlite3` directory and tables at app startup if they do not exist.

19. **Can the local SQLite database be used on any cloud host?**  
    Not safely by default. Some hosts erase local files on restart, and multiple instances do not share a local file. A persistent disk for one instance or a managed database is needed, planned carefully.

20. **What would you improve next?**  
    Add verified integration with a managed database for scale, richer category/unit mappings, partial allocation with recipient consent, and broader experiments with varied inputs.
