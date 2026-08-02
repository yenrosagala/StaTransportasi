import dash
from dash import Dash, html, dcc
import dash_bootstrap_components as dbc # Optional, great for UI/UX

# Initialize the main app with Dash pages or a simple router
app = Dash(__name__, use_pages=True, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Create a shared Navbar for UI/UX consistency
navbar = dbc.NavbarSimple(
    children=[
        dbc.NavItem(dbc.NavLink("Pariwisata", href="/pariwisata")),
        dbc.NavItem(dbc.NavLink("Transportasi", href="/transportasi")),
    ],
    brand="Dashboard Integrasi",
    brand_href="/",
    color="primary",
    dark=True,
)

app.layout = html.Div([
    navbar,
    dash.page_container # This dynamically renders the active page
])

if __name__ == '__main__':
    app.run_server(debug=True)
