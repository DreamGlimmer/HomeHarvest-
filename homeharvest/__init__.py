import pandas as pd
from typing import Union
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from .core.scrapers import ScraperInput
from .core.scrapers.redfin import RedfinScraper
from .core.scrapers.realtor import RealtorScraper
from .core.scrapers.zillow import ZillowScraper
from .core.scrapers.models import ListingType, Property, SiteName
from .exceptions import InvalidSite, InvalidListingType


_scrapers = {
    "redfin": RedfinScraper,
    "realtor.com": RealtorScraper,
    "zillow": ZillowScraper,
}


def validate_input(site_name: str, listing_type: str) -> None:
    if site_name.lower() not in _scrapers:
        raise InvalidSite(f"Provided site, '{site_name}', does not exist.")

    if listing_type.upper() not in ListingType.__members__:
        raise InvalidListingType(
            f"Provided listing type, '{listing_type}', does not exist."
        )


def get_ordered_properties(result: Property) -> list[str]:
    return [
        "property_url",
        "site_name",
        "listing_type",
        "property_type",
        "status_text",
        "currency",
        "price",
        "apt_min_price",
        "apt_max_price",
        "apt_min_sqft",
        "apt_max_sqft",
        "apt_min_beds",
        "apt_max_beds",
        "apt_min_baths",
        "apt_max_baths",
        "tax_assessed_value",
        "square_feet",
        "price_per_sqft",
        "beds",
        "baths",
        "lot_area_value",
        "lot_area_unit",
        "street_address",
        "unit",
        "city",
        "state",
        "zip_code",
        "country",
        "posted_time",
        "bldg_min_beds",
        "bldg_min_baths",
        "bldg_min_area",
        "bldg_unit_count",
        "bldg_name",
        "stories",
        "year_built",
        "agent_name",
        "mls_id",
        "description",
        "img_src",
        "latitude",
        "longitude",
    ]


def process_result(result: Property) -> pd.DataFrame:
    prop_data = result.__dict__

    prop_data["site_name"] = prop_data["site_name"].value
    prop_data["listing_type"] = prop_data["listing_type"].value.lower()
    if "property_type" in prop_data and prop_data["property_type"] is not None:
        prop_data["property_type"] = prop_data["property_type"].value.lower()
    else:
        prop_data["property_type"] = None
    if "address" in prop_data:
        address_data = prop_data["address"]
        prop_data["street_address"] = address_data.street_address
        prop_data["unit"] = address_data.unit
        prop_data["city"] = address_data.city
        prop_data["state"] = address_data.state
        prop_data["zip_code"] = address_data.zip_code
        prop_data["country"] = address_data.country

        del prop_data["address"]

    properties_df = pd.DataFrame([prop_data])
    properties_df = properties_df[get_ordered_properties(result)]

    return properties_df


def _scrape_single_site(
    location: str, site_name: str, listing_type: str
) -> pd.DataFrame:
    """
    Helper function to scrape a single site.
    """
    validate_input(site_name, listing_type)

    scraper_input = ScraperInput(
        location=location,
        listing_type=ListingType[listing_type.upper()],
        site_name=SiteName.get_by_value(site_name.lower()),
    )

    site = _scrapers[site_name.lower()](scraper_input)
    results = site.search()

    properties_dfs = [process_result(result) for result in results]
    properties_dfs = [
        df.dropna(axis=1, how="all") for df in properties_dfs if not df.empty
    ]
    if not properties_dfs:
        return pd.DataFrame()

    return pd.concat(properties_dfs, ignore_index=True)


def scrape_property(
    location: str,
    site_name: Union[str, list[str]] = None,
    listing_type: str = "for_sale",
) -> pd.DataFrame:
    """
    Scrape property from various sites from a given location and listing type.

    :returns: pd.DataFrame
    :param location: US Location (e.g. 'San Francisco, CA', 'Cook County, IL', '85281', '2530 Al Lipscomb Way')
    :param site_name: Site name or list of site names (e.g. ['realtor.com', 'zillow'], 'redfin')
    :param listing_type: Listing type (e.g. 'for_sale', 'for_rent', 'sold')
    :return: pd.DataFrame containing properties
    """
    if site_name is None:
        site_name = list(_scrapers.keys())

    if not isinstance(site_name, list):
        site_name = [site_name]

    results = []

    if len(site_name) == 1:
        final_df = _scrape_single_site(location, site_name[0], listing_type)
        results.append(final_df)
    else:
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(
                    _scrape_single_site, location, s_name, listing_type
                ): s_name
                for s_name in site_name
            }

            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                results.append(result)

    results = [df for df in results if not df.empty and not df.isna().all().all()]

    if not results:
        return pd.DataFrame()

    final_df = pd.concat(results, ignore_index=True)

    columns_to_track = ["street_address", "city", "unit"]

    #: validate they exist, otherwise create them
    for col in columns_to_track:
        if col not in final_df.columns:
            final_df[col] = None

    final_df = final_df.drop_duplicates(
        subset=["street_address", "city", "unit"], keep="first"
    )
    return final_df
