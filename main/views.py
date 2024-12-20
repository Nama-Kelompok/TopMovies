from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse

from .utils.distributor import fetch_all_distributors
from .utils.director import process_director 
from .utils.actor import process_actors
from .utils.screenwriter import fetch_all_screenwriters
from .utils.review import fetch_review_scores
from .utils.time import format_running_time
from .utils.additional import fetch_country_of_origin, fetch_awards_received, fetch_filming_locations
from .utils.supporting import (
    fetch_director_of_photography,
    fetch_film_editor,
    fetch_production_designer,
    fetch_costume_designer,
    fetch_composer,
    fetch_producer
)

from .utils.sparql import local_sparql 

def landing_page(request):
    return render(request, "landing.html")

def main_page(request):
    search = request.GET.get("search", "")
    context = {"search": search}
    return render(request, "main.html", context)

def search_movies(request):
    PAGE_SIZE = 20
    search_input = request.GET.get("movie", "").strip()
    sort_input = request.GET.get("sort", "").strip()
    page = int(request.GET.get("page", 1))
    
    # Menentukan ORDER BY berdasarkan sort_input
    if sort_input == "alphabet_asc":
        order_by = "ASC(?movieName)"
    elif sort_input == "budget":
        order_by = "DESC(?budget)"
    elif sort_input == "title_desc":
        order_by = "DESC(?movieName)"
    elif sort_input == "release_year":
        order_by = "DESC(xsd:integer(?releaseYear))"
    elif sort_input == "rating":
        order_by = "DESC(xsd:decimal(?rating))"
    elif sort_input == "international_sales":
        order_by = "DESC(xsd:decimal(?internationalSales))"
    else:
        order_by = "ASC(?movieName)"
    
    sparql_query = f"""
    PREFIX : <http://nama-kelompok.org/data/> 
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX v: <http://nama-kelompok.org/vocab#>
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    SELECT DISTINCT ?movieId ?movieName 
           (COALESCE(?wikipediaPosterLink, ?otherPosterLink) AS ?finalPosterLink) 
           ?releaseYear ?rating ?internationalSales (SAMPLE(xsd:integer(?budget)) AS ?normalizedBudget) WHERE {{
        ?movieId rdf:type :Movie .
        ?movieId rdfs:label ?movieName .
        
        OPTIONAL {{ ?movieId v:posterLink ?wikipediaPosterLink . 
                   FILTER(CONTAINS(STR(?wikipediaPosterLink), "upload.wikimedia.org")) }}
        
        OPTIONAL {{ ?movieId v:posterLink ?otherPosterLink .
                   FILTER(!CONTAINS(STR(?otherPosterLink), "upload.wikimedia.org")) }}
                   
        OPTIONAL {{ ?movieId v:releaseYear ?releaseYear . }}
        OPTIONAL {{ ?movieId v:imdbRating ?rating . }}
        OPTIONAL {{ ?movieId v:internationalSales ?internationalSales . }}
        OPTIONAL {{ ?movieId v:budget ?budget . }}
        OPTIONAL {{ ?movieId v:genre ?genre . }}
        
        FILTER(
            REGEX(?movieName, ".*{search_input}.*", "i") || 
            (BOUND(?genre) && REGEX(?genre, ".*{search_input}.*", "i"))
        )
    }}GROUP BY ?movieId ?movieName ?wikipediaPosterLink ?otherPosterLink 
          ?releaseYear ?rating ?internationalSales
    ORDER BY {order_by}
    OFFSET {(page - 1) * PAGE_SIZE}
    LIMIT {PAGE_SIZE + 1}
    """

    local_sparql.setQuery(sparql_query)
    try:
        query_results = local_sparql.query().convert()["results"]["bindings"]

        hasNextPage = False
        if len(query_results) > PAGE_SIZE:
            hasNextPage = True
            query_results = query_results[:PAGE_SIZE]

        data = {
            "hasNextPage": hasNextPage,
            "currentPage": page,
            "movies": []
        }

        for movie in query_results:
            tempData = {
                "movieId": movie['movieId']["value"],
                "movieName": movie["movieName"]["value"],
                "posterLink": movie.get("finalPosterLink", {}).get("value", "/static/user/images/default.jpg"),
                "releaseYear": movie.get("releaseYear", {}).get("value", "Unknown")
            }
            data["movies"].append(tempData)

        return JsonResponse(data)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# Mengambil data dari movie
def get_movie_data(request, id):
    user_agent = request.headers.get("user-agent", "")
    if "Mozilla" not in user_agent:
        return HttpResponseRedirect(reverse("main:movie_page", kwargs={"id": id}))

    context = {"id": id}
    return JsonResponse(context)

# Mengambil detail dari movie
def get_movie_details(request, uri=None):
    if not uri.startswith("http://"):
        uri = f"http://nama-kelompok.org/data/{uri}"

    # Query SPARQL fetch data lokal
    sparql_query = f"""
    PREFIX : <http://nama-kelompok.org/data/> 
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX v: <http://nama-kelompok.org/vocab#>
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    SELECT DISTINCT ?movies ?title ?director 
           (GROUP_CONCAT(DISTINCT ?genre; separator=", ") AS ?genres) 
           ?rating ?metaScore ?information 
           (COALESCE(?wikipediaPosterLink, ?otherPosterLink) AS ?finalPosterLink)
           ?releaseYear ?runningTime 
           (GROUP_CONCAT(DISTINCT ?star; separator=", ") AS ?stars) 
           ?votes ?wikidataUri ?distributor
           ?budget ?certificate ?domesticOpening ?domesticSales 
           ?internationalSales ?license ?releaseDate
    WHERE {{
        ?movies rdf:type :Movie .
        ?movies rdfs:label ?title .
        
        OPTIONAL {{ ?movies v:director ?director. }}
        OPTIONAL {{ ?movies v:distributor ?distributor. }}
        OPTIONAL {{ ?movies v:genre ?genre. }}
        OPTIONAL {{ ?movies v:imdbRating ?rating. }}
        OPTIONAL {{ ?movies v:metaScore ?metaScore. }}
        OPTIONAL {{ ?movies v:movieInfo ?information. }}

        OPTIONAL {{ ?movies v:posterLink ?wikipediaPosterLink . 
        FILTER(CONTAINS(STR(?wikipediaPosterLink), "upload.wikimedia.org")) }}
        
        OPTIONAL {{ ?movies v:posterLink ?otherPosterLink .
        FILTER(!CONTAINS(STR(?otherPosterLink), "upload.wikimedia.org")) }}
        OPTIONAL {{ ?movies v:releaseYear ?releaseYear. }}
        OPTIONAL {{ ?movies v:runningTime ?runningTime. }}
        OPTIONAL {{ ?movies v:star ?star. }}
        OPTIONAL {{ ?movies v:votes ?votes. }}
        OPTIONAL {{ ?movies v:wikidataUri ?wikidataUri. }}
        OPTIONAL {{ ?movies v:budget ?budget. }}
        OPTIONAL {{ ?movies v:certificate ?certificate. }}
        OPTIONAL {{ ?movies v:domesticOpening ?domesticOpening. }}
        OPTIONAL {{ ?movies v:domesticSales ?domesticSales. }}
        OPTIONAL {{ ?movies v:internationalSales ?internationalSales. }}
        OPTIONAL {{ ?movies v:license ?license. }}
        OPTIONAL {{ ?movies v:releaseDate ?releaseDate. }}
        VALUES ?movies {{ <{uri}> }} 
    }}
    GROUP BY ?movies ?title ?director ?rating ?metaScore ?information 
         ?releaseYear ?runningTime ?votes ?wikidataUri ?distributor
         ?budget ?certificate ?domesticOpening ?domesticSales 
         ?internationalSales ?license ?releaseDate 
         ?wikipediaPosterLink ?otherPosterLink
    LIMIT 1
    """
    local_sparql.setQuery(sparql_query)
    try:
        results = local_sparql.query().convert()

        attributes = [
            "director", "genres", "rating", "metaScore", "information",
            "finalPosterLink", "releaseYear", "runningTime", 
            "stars", "votes", "wikidataUri", "distributor",
            "budget", "certificate", "domesticOpening", "domesticSales",
            "internationalSales", "license", "releaseDate"
        ]

        if results["results"]["bindings"]:
            result = results["results"]["bindings"][0]
            data_movie = {
                "movies": result["movies"]["value"],
                "title": result["title"]["value"],
            }

            for attr in attributes:
                if attr in result:
                    value = result[attr]["value"]
                    # Konversi tipe data sesuai kebutuhan
                    if attr in ["budget", "domesticOpening", "domesticSales", "internationalSales", "votes"]:
                        try:
                            value = int(value)
                        except ValueError:
                            value = value 
                    elif attr in ["releaseDate"]:
                        value = value.split("^^")[0].strip('"')
                    data_movie[attr] = value
                else:
                    data_movie[attr] = f"Tidak terdapat data {attr}"

            # Mengambil nama aktor
            actors_final = process_actors(data_movie)
            data_movie["stars"] = actors_final

            # Mengambil nama distributor
            distributors = fetch_all_distributors(data_movie["wikidataUri"])
            data_movie["distributors"] = distributors

            # Mengambil nama director menggunakan fungsi process_director
            data_movie = process_director(data_movie)

            # Mengambil nama screenwriter
            screenwriters = fetch_all_screenwriters(data_movie["wikidataUri"])
            data_movie["screenwriters"] = screenwriters

            # Mengambil running time film
            running_time = data_movie.get("runningTime", "")
            data_movie["runningTime"] = format_running_time(running_time)

            # Mengambil review scores, tambahkan rating IMDb jika perlu
            imdb_rating = data_movie.get("rating")
            reviews = fetch_review_scores(data_movie["wikidataUri"], imdb_rating)
            data_movie["reviews"] = reviews

            # Mengambil data tambahan
            countries = fetch_country_of_origin(data_movie["wikidataUri"])
            data_movie["countries_of_origin"] = countries

            awards = fetch_awards_received(data_movie["wikidataUri"])
            data_movie["awards_received"] = awards

            filming_locations = fetch_filming_locations(data_movie["wikidataUri"])
            data_movie["filming_locations"] = filming_locations

            # Fetch crew members
            data_movie["director_of_photography"] = fetch_director_of_photography(data_movie["wikidataUri"])
            data_movie["film_editor"] = fetch_film_editor(data_movie["wikidataUri"])
            data_movie["production_designer"] = fetch_production_designer(data_movie["wikidataUri"])
            data_movie["costume_designer"] = fetch_costume_designer(data_movie["wikidataUri"])
            data_movie["composer"] = fetch_composer(data_movie["wikidataUri"])
            data_movie["producer"] = fetch_producer(data_movie["wikidataUri"])

            # Menetapkan photoUrl
            poster_link = data_movie.get("finalPosterLink", "").strip() 
            if poster_link and poster_link != "Tidak terdapat data posterLink":
                data_movie["photoUrl"] = poster_link
            else:
                data_movie["photoUrl"] = "{% static 'user/images/placeholder.jpg' %}"

            return render(request, "detail_movie.html", {"movie": data_movie})

        else:
            return JsonResponse({"error": "Film tidak ditemukan"}, status=404)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)