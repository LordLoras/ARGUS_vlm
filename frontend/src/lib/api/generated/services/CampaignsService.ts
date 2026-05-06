/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AcceptDiscoveryRequest } from '../models/AcceptDiscoveryRequest';
import type { AssignAdsRequest } from '../models/AssignAdsRequest';
import type { CampaignCreate } from '../models/CampaignCreate';
import type { CampaignPatch } from '../models/CampaignPatch';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class CampaignsService {
    /**
     * List Campaigns
     * @param brand
     * @param createdBy
     * @param q
     * @param limit
     * @param offset
     * @returns any Successful Response
     * @throws ApiError
     */
    public static listCampaignsApiCampaignsGet(
        brand?: (string | null),
        createdBy?: (string | null),
        q?: (string | null),
        limit: number = 20,
        offset?: number,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/campaigns',
            query: {
                'brand': brand,
                'created_by': createdBy,
                'q': q,
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Campaign
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static createCampaignApiCampaignsPost(
        requestBody: CampaignCreate,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/campaigns',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Discover
     * @returns any Successful Response
     * @throws ApiError
     */
    public static discoverApiCampaignsDiscoverPost(): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/campaigns/discover',
        });
    }
    /**
     * Accept Discovered
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static acceptDiscoveredApiCampaignsDiscoverAcceptPost(
        requestBody: AcceptDiscoveryRequest,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/campaigns/discover/accept',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Campaign
     * @param campaignId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getCampaignApiCampaignsCampaignIdGet(
        campaignId: string,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/campaigns/{campaign_id}',
            path: {
                'campaign_id': campaignId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Campaign
     * @param campaignId
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static patchCampaignApiCampaignsCampaignIdPatch(
        campaignId: string,
        requestBody: CampaignPatch,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/campaigns/{campaign_id}',
            path: {
                'campaign_id': campaignId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Campaign
     * @param campaignId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteCampaignApiCampaignsCampaignIdDelete(
        campaignId: string,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/campaigns/{campaign_id}',
            path: {
                'campaign_id': campaignId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Assign Ads
     * @param campaignId
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static assignAdsApiCampaignsCampaignIdAdsPost(
        campaignId: string,
        requestBody: AssignAdsRequest,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/campaigns/{campaign_id}/ads',
            path: {
                'campaign_id': campaignId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Unassign Ad
     * @param campaignId
     * @param adId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static unassignAdApiCampaignsCampaignIdAdsAdIdDelete(
        campaignId: string,
        adId: string,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/campaigns/{campaign_id}/ads/{ad_id}',
            path: {
                'campaign_id': campaignId,
                'ad_id': adId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
