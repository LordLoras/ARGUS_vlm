/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AdPatch } from '../models/AdPatch';
import type { Body_upload_ad_api_ads_upload_post } from '../models/Body_upload_ad_api_ads_upload_post';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AdsService {
    /**
     * Upload Ad
     * @param formData
     * @returns any Successful Response
     * @throws ApiError
     */
    public static uploadAdApiAdsUploadPost(
        formData: Body_upload_ad_api_ads_upload_post,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ads/upload',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Ads
     * @param brand
     * @param category
     * @param status
     * @param q
     * @param limit
     * @param offset
     * @returns any Successful Response
     * @throws ApiError
     */
    public static listAdsApiAdsGet(
        brand?: (string | null),
        category?: (string | null),
        status?: (string | null),
        q?: (string | null),
        limit: number = 50,
        offset?: number,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/ads',
            query: {
                'brand': brand,
                'category': category,
                'status': status,
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
     * Get Ad
     * @param adId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getAdApiAdsAdIdGet(
        adId: string,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/ads/{ad_id}',
            path: {
                'ad_id': adId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Ad
     * @param adId
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static patchAdApiAdsAdIdPatch(
        adId: string,
        requestBody: AdPatch,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/ads/{ad_id}',
            path: {
                'ad_id': adId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Ad
     * @param adId
     * @param cleanupArtifacts
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteAdApiAdsAdIdDelete(
        adId: string,
        cleanupArtifacts: boolean = false,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/ads/{ad_id}',
            path: {
                'ad_id': adId,
            },
            query: {
                'cleanup_artifacts': cleanupArtifacts,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Frames
     * @param adId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getFramesApiAdsAdIdFramesGet(
        adId: string,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/ads/{ad_id}/frames',
            path: {
                'ad_id': adId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Evidence
     * @param adId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getEvidenceApiAdsAdIdEvidenceGet(
        adId: string,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/ads/{ad_id}/evidence',
            path: {
                'ad_id': adId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Similar
     * @param adId
     * @param k
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getSimilarApiAdsAdIdSimilarGet(
        adId: string,
        k: number = 5,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/ads/{ad_id}/similar',
            path: {
                'ad_id': adId,
            },
            query: {
                'k': k,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
