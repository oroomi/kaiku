# /admin, the keyed hub
The hub puts the console, the FIWARE views, the three-sentence story and the other links on one page for the team, Fonecta and the judges.
Key rule is the same as /console: /admin?key=KEY (or the key header or cookie) gives 200, anything else gives 403 and a one-line notice.
The key reaches the HTML only inside the two keyed links (judge page and console); it is never echoed from a header or cookie.
The contact box, Run the chain (24.12.) and Reset demo reuse the console's element ids and /static/console.js unchanged.
The three FIWARE panels (Aura, the city twin with 813 stores, the room) show a poster; the iframe is created only on "Load the live view", so three WebGL maps never start together.
The city iframe uses ?embed=1 (nav hidden); /aura and /room have no embed mode, so their iframes show the normal page header.
Posters are 960 px JPEGs of our own live pages; the Aura and city ones are dark because headless Chrome renders WebGL maps late. Retake them with bin/shot.py on a real GPU if wanted.
Did not work: a first test version imported the app at module level and broke test_core (settings are read at import); the test now imports it lazily.
